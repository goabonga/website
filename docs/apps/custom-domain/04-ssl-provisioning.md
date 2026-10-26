# SSL provisioning

This feature turns a domain whose DNS is correct into a served HTTPS site: it
writes the HTTP-only nginx configuration, asks Let's Encrypt for a certificate
through certbot, then writes the full HTTPS configuration. The work runs in a
Celery worker because it takes minutes and needs privileged commands.

It adds the `certbot_service`, the Celery application, the synchronous
database session the workers use and the provisioning tasks.

## Certbot service

`custom_domain.services.certbot.certbot_service`. certbot and openssl run
through the privileged helper described in the nginx rendering page, never
directly: the service account can not read the certificate directory nor run
certbot.

- `provision_certificate(domain)` asks the helper to run `certbot certonly
  --webroot --webroot-path <CERTBOT_WEBROOT> -d <domain> --email <CERTBOT_EMAIL>
  --agree-tos --non-interactive --quiet`. The webroot and the e-mail are
  settings, fixed by the sudoers rule, not parameters. When `CERTBOT_ENABLED`
  is false it does nothing and reports success. Failures are translated: a rate
  limit answers *Let's Encrypt rate limit exceeded. Try again later.*, a failed
  challenge answers *ACME challenge failed. Verify DNS configuration.*, anything
  else returns the first 500 characters of certbot's stderr. A missing setting
  (for example an empty `CERTBOT_EMAIL`) is reported as a failure naming the
  variable. On success the expiry date is read from the certificate.
- `check_certificate(domain)` asks the helper for the validity dates of
  `<LETSENCRYPT_DIR>/live/<domain>/fullchain.pem` (`openssl x509 -noout -dates`)
  and returns a `CertificateInfo` (issue date, expiry date, days until expiry),
  or `None` when the certificate is missing or unreadable.
- `renew_certificate(domain)` asks the helper to run `certbot renew --cert-name
  <domain>`.
- `revoke_certificate(domain)` asks the helper to run `certbot revoke --cert-path
  <LETSENCRYPT_DIR>/live/<domain>/cert.pem --delete-after-revoke`. A domain
  without a certificate succeeds with the message *Certificate does not exist*.

The helper commands added by this feature are:

| Command | Argument | What it does |
| --- | --- | --- |
| `certbot-issue` | domain | `certbot certonly --webroot ...` as above. |
| `certbot-renew` | domain | `certbot renew --cert-name <domain> --non-interactive --quiet`. |
| `certbot-revoke` | domain | `certbot revoke --cert-path ... --delete-after-revoke`, or prints `certificate absent` and succeeds. |
| `cert-dates` | domain | Prints `openssl x509 -in .../fullchain.pem -noout -dates`; exits with status 3 when there is no certificate. |

Their options (`--certbot-bin`, `--openssl-bin`, `--webroot`, `--letsencrypt-dir`,
`--email`) come from the settings below and are fixed by the sudoers rule.

## Celery application

`custom_domain.celery:celery_app` uses JSON serialization, UTC, late
acknowledgement, `task_reject_on_worker_lost`, a prefetch multiplier of 1 and
time limits taken from `CELERY_TASK_SOFT_TIME_LIMIT_SECONDS` and
`CELERY_TASK_TIME_LIMIT_SECONDS`. Tasks are auto-discovered from
`custom_domain.tasks`.

The queue is a setting, `CELERY_QUEUE` (default `custom-domain`). It is both the
default queue of the application and the route of every `custom_domain.tasks.*`
task, so a worker started with `--queues=<CELERY_QUEUE>` consumes everything the
API and beat publish. Without that, tasks would go to Celery's own `celery`
queue and a worker started on a named queue would never see them.

Workers read the database through a synchronous SQLAlchemy engine
(`custom_domain.database.get_sync_db`) that always uses the `psycopg2` driver:
a plain `postgresql://` URL is turned into `postgresql+psycopg2://`.

Start a worker with:

```bash
uv run --package custom-domain celery -A custom_domain.celery:celery_app worker --loglevel=info --queues=custom-domain
```

## Tasks

### `provision_domain_ssl(domain_id)`

1. Loads the domain (ignored when it does not exist or is soft-deleted).
2. Picks the nginx template (`resolve_template`): the domain's own active
   template, otherwise the active default template of the domain's client,
   otherwise the active global default template, otherwise the files shipped
   with the package.
3. Sets the status to `ssl_provisioning`.
4. Writes the HTTP-only configuration and reloads nginx (step `nginx_http`).
5. Requests the certificate (step `certbot`).
6. Writes the HTTPS configuration and reloads nginx (step `nginx_https`).
7. Marks the domain `active`, stores `ssl_provisioned_at` and `ssl_expires_at`
   and clears `error_message`.

If certbot fails the domain is marked `failed` and keeps certbot's message in
`error_message`. A *rate limit* failure is retried instead (up to
`PROVISIONING_MAX_RETRIES` retries, after `PROVISIONING_RETRY_DELAY_SECONDS` then
twice that, and so on) and the domain stays in `ssl_provisioning` in the
meantime. Any other exception marks the domain `failed` with the first 500
characters of the error.

The source application caught the `Retry` exception with its generic error
handler, so a rate-limited domain was failed immediately and never retried. The
migrated task re-raises it so that Celery reschedules the task as intended.

### `deprovision_domain(domain_id, revoke_certificate=True)`

Takes a domain out of service. It runs in the worker because it needs the
privileged helper; the API never does it.

1. If the domain is not already `deprovisioning` (the API sets that status; the
   maintenance tasks do not) it is moved there and a `status_change` event is
   published.
2. The nginx file is removed and nginx reloaded. A failure is retried (same
   settings as provisioning); when the retries are exhausted the domain is marked
   `failed` with the error, an `error` event with the code
   `DEPROVISIONING_FAILED` is published and the domain is kept.
3. If `CERTBOT_REVOKE_ON_DEPROVISION` is true and the caller did not pass
   `revoke_certificate=False` the certificate is revoked and deleted. The API
   revokes (an explicit deletion by the client); the maintenance tasks, which retire
   domains on their own initiative (stale or no longer pointing at the platform),
   do not: a transient DNS problem must not destroy a certificate. A failed
   revocation is logged and does not stop the deletion.
4. The domain is soft-deleted (`deleted_at`, kept if the maintenance tasks had
   already set it) and a `completed` event with `deleted: true` is published.

### Progress events

Both the provisioning and the verification tasks publish progress events to
Redis so that clients can follow them (see the events feature). Each event is
JSON `{"type": ..., "payload": {..., "timestamp": <ISO 8601 UTC>}}`, published
on the channel `domain:<id>:events` and pushed to the list
`domain:<id>:event_history` (the last `EVENT_HISTORY_SIZE` entries are kept, for
`EVENT_HISTORY_TTL_SECONDS`). The publishing code is
`custom_domain.services.events.publish_event`.
Provisioning emits `status_change`, `step_started`, `step_completed`,
`step_failed`, `completed` and `error` events, with the steps `nginx_http`,
`certbot` and `nginx_https`. Publishing failures are logged and ignored.

The timestamp is a plain ISO 8601 value (`2026-01-01T12:00:00+00:00`); the
source appended a stray `Z` after the offset, which the history endpoint could
not parse.

## Settings

| Variable | Default | Description |
| --- | --- | --- |
| `CELERY_BROKER_URL` | `redis://localhost:6379/0` | Celery broker. |
| `CELERY_RESULT_BACKEND` | `redis://localhost:6379/1` | Celery result backend. |
| `CELERY_QUEUE` | `custom-domain` | Default queue and route of every task; start the worker with `--queues` set to the same name. |
| `CELERY_TASK_SOFT_TIME_LIMIT_SECONDS` | `270` | Soft time limit of a task. |
| `CELERY_TASK_TIME_LIMIT_SECONDS` | `300` | Hard time limit of a task. |
| `CERTBOT_ENABLED` | `true` | Set to `false` to skip certificate requests (useful in development). |
| `CERTBOT_EMAIL` | empty (required when certbot is enabled) | Contact address given to Let's Encrypt. |
| `CERTBOT_BIN` | empty (required) | Absolute path of `certbot`. |
| `OPENSSL_BIN` | empty (required) | Absolute path of `openssl`, used to read the expiry date. |
| `CERTBOT_REVOKE_ON_DEPROVISION` | `true` | Revoke the certificate when a domain is deprovisioned. |
| `PROVISIONING_MAX_RETRIES` | `2` | Retries of provisioning and deprovisioning. |
| `PROVISIONING_RETRY_DELAY_SECONDS` | `600` | Delay before the first retry; it doubles each time. |
| `EVENT_HISTORY_SIZE` | `100` | Events kept per domain. |
| `EVENT_HISTORY_TTL_SECONDS` | `86400` | Lifetime of the event history. |
| `REDIS_URL` | `redis://localhost:6379/13` | Redis used for the progress events. |

The nginx, helper and path settings are listed in the nginx rendering page. The
worker needs one sudoers rule per helper command (see the deployment page).

## How it is tested

- pytest: `test_services_certbot.py` (helper commands, failure translation,
  certificate parsing, renewal, revocation, missing settings),
  `test_privileged_helper_certbot.py` (the real helper with a fake certbot and
  openssl), `test_tasks_provisioning.py` (success, certbot failure, template
  resolution, retry propagation, error handling, deprovisioning with its
  retries and revocation), `test_services_events.py` (history size and
  lifetime), `test_celery.py` (queue, routes, time limits as settings),
  `test_database.py` (URL conversion and sessions, including the synchronous
  one) and the Celery settings assertion in `test_config.py`.
- behave: `features/ssl_provisioning.feature` runs the Celery tasks in-process
  against an in-memory database with nginx and certbot faked: *A verified
  domain becomes active*, *A certificate failure marks the domain as failed*,
  *A Let's Encrypt rate limit schedules a retry*, *A deleted domain is ignored*,
  *Deprovisioning removes the nginx configuration and the certificate*, *A domain
  removed by maintenance is marked as deprovisioning first*, *Tasks are published
  to the queue the worker consumes*, *Certbot requests a webroot certificate
  through the helper*, *A missing e-mail is reported instead of guessed* and
  *Certbot can be disabled*. No Redis, nginx, certbot or Celery
  worker is involved.
