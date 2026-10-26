# Deployment and local development

This page describes how the service is run: the three processes it is made of,
what they need on the host, the settings to provide and how to start a local
environment. It reflects the code of the previous pages.

## Processes

The service is one code base started three ways. All of them run from the
same checkout and share the settings below.

| Process | Command | Role |
| --- | --- | --- |
| API | `gunicorn -k uvicorn.workers.UvicornWorker custom_domain.main:app` | The FastAPI application. It runs without any privilege and never starts `sudo`: deleting a domain and validating a template are delegated to the worker. Production runs two workers behind a Unix socket, fronted by nginx and reachable from the VPN only. |
| Worker | `celery -A custom_domain.celery:celery_app worker --loglevel=info --concurrency=2 --queues=<CELERY_QUEUE>` | Runs DNS verification, SSL provisioning, deprovisioning, template validation, the webhook deliveries and the maintenance tasks. It is the only process that uses the privileged helper. |
| Beat | `celery -A custom_domain.celery:celery_app beat --loglevel=info` | Publishes the periodic tasks, to the same queue. Exactly one instance may run. |

`gunicorn` and `uvicorn` are declared dependencies of the package for that
reason. The package also installs the `custom-domain` command (CLI page).

**The queue.** Every task, the periodic ones included, is published to the queue
named by `CELERY_QUEUE` (default `custom-domain`), and the worker must consume that
queue (`--queues=custom-domain`, or `-Q`). A worker started on another queue, or the
default one, would never receive anything. If the queue name is changed, change it
for the API, beat and worker alike.

The production definition of these three units (names `custom_domain`,
`custom_domain_worker` and `custom_domain_beat` in the applications inventory of
the VPS repository) uses the `python_app` role: a `gunicorn` unit with a socket
and an internal nginx vhost with a health check on `/health`, a `celery_worker`
unit consuming the queue `custom-domain`, and a `celery_beat` unit. The API unit
runs the Alembic migrations on every deploy. The module paths in that inventory must
be updated to the new package layout: `app.main:app` becomes `custom_domain.main:app`
and `app.celery:celery_app` becomes `custom_domain.celery:celery_app`. The Celery task
names changed accordingly (`app.tasks.*` is now `custom_domain.tasks.*`), so drain the
queue before switching versions.

## Host requirements

- **PostgreSQL** with a database for the service, reached through a Unix
  socket (`DATABASE_URL=postgresql:///custom_domain`, peer authentication).
  The API uses `asyncpg`, the worker and Alembic use `psycopg2`.
- **Redis**: database 13 for caches and progress events
  (`REDIS_URL`), databases 0 and 1 for the Celery broker and result backend.
- **nginx** and **certbot** on the same host as the worker, with the webroot
  directory served for `/.well-known/acme-challenge/` and `openssl` for reading
  certificate dates.
- **The privileged helper**, below, and the sudoers rules for it.
- The OAuth2 server of the platform for token validation (OAuth2
  authentication page).

### The privileged helper

The worker never writes to `/etc/nginx` nor runs certbot itself. Every privileged
operation is one command of a single standard-library script,
`custom_domain/privileged_helper.py`, that the worker starts with `sudo -n` (nginx
rendering page describes the commands and their validation). Install it once:

```bash
install -o root -g root -m 0755 \
    "$(python -c 'import custom_domain.privileged_helper as h; print(h.__file__)')" \
    /usr/local/sbin/custom-domain-privileged        # the path you set in PRIVILEGED_HELPER
install -d -o custom_domain -g custom_domain -m 0750 /var/lib/custom-domain/staging  # PRIVILEGED_STAGING_DIR
```

The script must be owned by root and not writable by anyone else, as must the
`nginx`, `systemctl`, `certbot` and `openssl` binaries it runs (it refuses
otherwise when it runs as root). The system Python 3.11 or later runs it; it does not
need the application's virtual environment. Reinstall it when the package is
updated, since the application and the helper must agree on the command table
(a test checks that the application only builds command lines the helper accepts).
The unit of the worker must allow `sudo`: no `NoNewPrivileges=yes`.

### Sudoers rules

The rules are generated from the settings so that they match exactly what the
application runs; `sudo` compares the arguments literally, which is why the options
are part of the rule and why the old rules (`tee`, `rm`, `cp /tmp/*`, `certbot
certonly *`) no longer apply. Print them on the worker host, with the worker's
environment:

```bash
custom-domain sudoers --user custom_domain
# or: python -m custom_domain.services.privileged --user custom_domain
```

With the example values `NGINX_SITES_DIR=/etc/nginx/sites-enabled`,
`NGINX_BIN=/usr/sbin/nginx`, `SYSTEMCTL_BIN=/usr/bin/systemctl`,
`CERTBOT_BIN=/usr/bin/certbot`, `OPENSSL_BIN=/usr/bin/openssl`,
`CERTBOT_WEBROOT=/var/www/certbot`, `LETSENCRYPT_DIR=/etc/letsencrypt`,
`CERTBOT_EMAIL=ops@example.com`, `PRIVILEGED_HELPER=/usr/local/sbin/custom-domain-privileged`
and `PRIVILEGED_STAGING_DIR=/var/lib/custom-domain/staging`, the nine rules are:

```text
custom_domain ALL=(root) NOPASSWD: /usr/local/sbin/custom-domain-privileged --sites-dir /etc/nginx/sites-enabled --config-prefix custom-domain- --staging-dir /var/lib/custom-domain/staging write-config *
custom_domain ALL=(root) NOPASSWD: /usr/local/sbin/custom-domain-privileged --sites-dir /etc/nginx/sites-enabled --config-prefix custom-domain- remove-config *
custom_domain ALL=(root) NOPASSWD: /usr/local/sbin/custom-domain-privileged --nginx-bin /usr/sbin/nginx test-nginx
custom_domain ALL=(root) NOPASSWD: /usr/local/sbin/custom-domain-privileged --systemctl-bin /usr/bin/systemctl --nginx-service nginx reload-nginx
custom_domain ALL=(root) NOPASSWD: /usr/local/sbin/custom-domain-privileged --nginx-bin /usr/sbin/nginx --staging-dir /var/lib/custom-domain/staging check-snippet *
custom_domain ALL=(root) NOPASSWD: /usr/local/sbin/custom-domain-privileged --certbot-bin /usr/bin/certbot --webroot /var/www/certbot --email ops@example.com certbot-issue *
custom_domain ALL=(root) NOPASSWD: /usr/local/sbin/custom-domain-privileged --certbot-bin /usr/bin/certbot certbot-renew *
custom_domain ALL=(root) NOPASSWD: /usr/local/sbin/custom-domain-privileged --certbot-bin /usr/bin/certbot --letsencrypt-dir /etc/letsencrypt certbot-revoke *
custom_domain ALL=(root) NOPASSWD: /usr/local/sbin/custom-domain-privileged --openssl-bin /usr/bin/openssl --letsencrypt-dir /etc/letsencrypt cert-dates *
```

The first two words of each rule fix the helper and all its options; only the
last `*` (a domain or a token) varies, and the helper accepts nothing but a
lower-case domain name or a 32-character hexadecimal token there. Anything that
changes a setting used in a rule (a path, the prefix, the e-mail) changes the rules:
regenerate and redeploy them together. Put them in a file under `/etc/sudoers.d/` and
check it with `visudo -cf`.

The API unit needs **no** sudoers rule.

## Settings

Every setting is an environment variable (or an entry of a `.env` file). The
tables of the previous pages give the meaning of each one; this is the set a
deployment normally defines. Settings without a default must be provided: an
operation that needs an empty one fails with a message naming the variable
(`ConfigurationError`).

| Process | Variables |
| --- | --- |
| API | `LOG_LEVEL`, `DOCS_ENABLED`, `DATABASE_URL`, `REDIS_URL`, `OAUTH2_ISSUER`, `OAUTH2_CLIENT_ID`, `OAUTH2_CLIENT_SECRET`, `OAUTH2_SWAGGER_CLIENT_ID`, `ADMIN_SCOPE`, `TOKEN_INTROSPECTION_CACHE_TTL`, `OAUTH2_CLIENT_CACHE_TTL`, `CELERY_BROKER_URL`, `CELERY_RESULT_BACKEND`, `CELERY_QUEUE`, `DEFAULT_CNAME_TARGET`, `TEMPLATE_VALIDATION_TIMEOUT_SECONDS`, `WEBHOOK_ALLOW_INSECURE_URLS`, `EVENT_HISTORY_SIZE`, `SSE_HEARTBEAT_INTERVAL`, `SSE_POLL_INTERVAL_SECONDS` |
| Worker | `DATABASE_URL`, `REDIS_URL`, `CELERY_BROKER_URL`, `CELERY_RESULT_BACKEND`, `CELERY_QUEUE`, `CELERY_TASK_SOFT_TIME_LIMIT_SECONDS`, `CELERY_TASK_TIME_LIMIT_SECONDS`, `NGINX_SITES_DIR`, `NGINX_CONFIG_PREFIX`, `NGINX_IPV4`, `NGINX_IPV6`, `NGINX_BIN`, `NGINX_SERVICE`, `SYSTEMCTL_BIN`, `CERTBOT_ENABLED`, `CERTBOT_EMAIL`, `CERTBOT_BIN`, `OPENSSL_BIN`, `CERTBOT_WEBROOT`, `LETSENCRYPT_DIR`, `CERTBOT_REVOKE_ON_DEPROVISION`, `SUDO_BIN`, `PRIVILEGED_HELPER`, `PRIVILEGED_STAGING_DIR`, `PRIVILEGED_TIMEOUT_SECONDS`, `PROVISIONING_MAX_RETRIES`, `PROVISIONING_RETRY_DELAY_SECONDS`, `DNS_TIMEOUT_SECONDS`, `DNS_VERIFICATION_MAX_RETRIES`, `DNS_VERIFICATION_RETRY_DELAY_SECONDS`, `CERTIFICATE_RENEWAL_DAYS`, `DOMAIN_ACTIVATION_TIMEOUT_HOURS`, `SOFT_DELETE_PURGE_DAYS`, `EVENT_HISTORY_SIZE`, `EVENT_HISTORY_TTL_SECONDS`, `WEBHOOK_TIMEOUT_SECONDS`, `WEBHOOK_MAX_RETRIES`, `WEBHOOK_RETRY_DELAY_SECONDS` |
| Beat | `DATABASE_URL`, `REDIS_URL`, `CELERY_BROKER_URL`, `CELERY_RESULT_BACKEND`, `CELERY_QUEUE`, `DNS_CHECK_INTERVAL_MINUTES`, `DOMAIN_HEALTH_CHECK_INTERVAL_HOURS`, `DOMAIN_HEALTH_CHECK_MINUTE`, `CERTIFICATE_EXPIRY_CHECK_CRON`, `STALE_CLEANUP_CRON`, `PURGE_DELETED_CRON` |

`OAUTH2_CLIENT_SECRET` is the only secret of the service itself. Provide it through
a systemd credential named `OAUTH2_CLIENT_SECRET` (`CREDENTIALS_DIRECTORY`) or the
environment; never commit it. The webhook secrets of the clients live in the
database (client administration page) and are supplied to the CLI through
`CUSTOM_DOMAIN_WEBHOOK_SECRET`.

`DOMAIN_ACTIVATION_TIMEOUT_HOURS` and `SOFT_DELETE_PURGE_DAYS` are read by the
worker (the maintenance tasks run there); the interval and cron settings are read by
beat when it builds the schedule.

## First start

```bash
export DATABASE_URL=postgresql:///custom_domain
uv run --package custom-domain alembic -c apps/custom-domain/alembic.ini upgrade head
uv run --package custom-domain custom-domain seed
uv run --package custom-domain custom-domain create-client --client-id my-app --name "My app" \
    --upstream /run/my-app.sock --cname apps.example.com
```

Then start the three processes. The API answers `GET /health` once it is up. To bring
a new application onto the service see the SaaS onboarding page.

## Local development

`compose.yml` starts a throw-away PostgreSQL 16 (port 5434, database
`custom_domain_test`, user and password `custom_domain`) and Redis 7 (port
6381):

```bash
docker compose -f apps/custom-domain/compose.yml up -d
export DATABASE_URL=postgresql://custom_domain:custom_domain@localhost:5434/custom_domain_test
export REDIS_URL=redis://localhost:6381/13
export CELERY_BROKER_URL=redis://localhost:6381/0
export CELERY_RESULT_BACKEND=redis://localhost:6381/1
export DOCS_ENABLED=true CERTBOT_ENABLED=false
uv run --package custom-domain alembic -c apps/custom-domain/alembic.ini upgrade head
uv run --package custom-domain custom-domain seed
uv run --package custom-domain uvicorn custom_domain.main:app --reload --port 8000
```

With `CERTBOT_ENABLED=false` certificate requests are skipped, but nginx
configuration is still installed through the helper and `sudo`, so run the worker on a
disposable host (or point `NGINX_SITES_DIR` and the helper at a directory you can write
to, with a sudoers rule for your user) and accept that those calls must succeed.

## Tests

Neither suite needs the compose services:

```bash
uv run --package custom-domain --group dev pytest apps/custom-domain
uv run --package custom-domain --group dev behave apps/custom-domain/features
```

pytest mocks the database, Redis, subprocesses and the OAuth2 server, except for the
privileged helper, whose tests run the real script against temporary directories and
fake `nginx`, `systemctl`, `certbot` and `openssl` programs. behave replaces the
infrastructure with in-process fakes (an in-memory SQLite database, a fake auth
server, recorded system commands).

**Not verified.** Neither suite has been run against a real PostgreSQL, Redis, nginx
or certbot, so the PostgreSQL-specific parts (the JSONB columns, the partial indexes
and the enum type, now with the `deprovisioning` value and the two later alembic
revisions) are only exercised through the rendered migration SQL and the SQLite
stand-in. The helper has not been run as root, through a real `sudoers` file or with
a real nginx; the sudoers rules are generated and compared with the command lines
the application builds, but `sudo`'s own matching has not been exercised. A Celery
broker that is down while a webhook is queued has not been tried.
