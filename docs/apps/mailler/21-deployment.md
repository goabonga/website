# Deployment

How mailler is run in production: three processes sharing one code base and
one PostgreSQL database. This page lists what a deployment has to provide;
the generic host preparation is done by the roles of the Ansible collection
described in the [Ansible documentation](../../ansible/roles/common.md).
The collection does not contain an application deployment role yet, so the
values below are the inputs such a role (or any other deployment tool) needs.

## Processes

| Process | Command | Notes |
| --- | --- | --- |
| API | `gunicorn mailler.main:app` with the uvicorn worker class | 2 workers, listens on a Unix socket behind a reverse proxy, health check on `GET /health` |
| Celery worker | `celery -A mailler.celery:celery_app worker -Q "$CELERY_QUEUE" --concurrency 4 --loglevel info` | Consumes the queue named by `CELERY_QUEUE` (`mailler` by default): sending, campaigns, status callbacks, maintenance and (if enabled) inbound tasks |
| Celery beat | `celery -A mailler.celery:celery_app beat --loglevel info` | Exactly one instance; needs only the broker settings |

Each process runs as the same unprivileged system user from a Python 3.11+
virtual environment that contains the `mailler` package (installed from the
`apps/mailler` workspace member), which also provides the `mailler`
[command](17-command-line.md) used to register clients and import templates.
The API is reachable only from the internal network; it is not exposed
publicly. The queue given to the worker (`-Q`) and `CELERY_QUEUE` of every
process must be the same.

The module paths changed with the move into the monorepo: the original
repository used `app.main:app` and `app.celery:celery_app`, and Celery task
names changed from `app.tasks.*` to `mailler.tasks.*`. Drain the old queue
before switching so that no message carries an old task name.

## How applications reach the API

The applications call `/api/v1` with a bearer token. Mailler does not care how
the request arrives:

- **Unix socket.** With gunicorn bound to a socket (`/run/mailler/mailler.sock`)
  whose group may use it, an application on the same host connects to the
  socket directly, for example with an `httpx` transport on
  `uds=/run/mailler/mailler.sock` and the base URL `http://localhost`. The
  account of the application must belong to the group that owns the socket.
- **HTTP.** Through the reverse proxy of the internal domain.

Either way the application obtains its token from the identity provider
(`OAUTH2_ISSUER`) with its own OAuth2 client, and that client must be
registered in the [client registry](15-authorized-clients.md).

## Backing services

- **PostgreSQL**: a dedicated `mailler` database owned by the service user,
  reached over the local socket with peer authentication
  (`DATABASE_URL=postgresql:///mailler`). The API uses the asyncpg driver and
  the workers psycopg2, both derived from the same URL. Prepared with the
  [postgres role](../../ansible/roles/postgres.md).
- **Redis**: Celery broker and result backend (`CELERY_BROKER_URL`,
  `CELERY_RESULT_BACKEND`) and the authentication caches (`REDIS_URL`).
  Prepared with the [redis role](../../ansible/roles/redis.md).
- **Identity provider**: the OAuth2 issuer (`OAUTH2_ISSUER`) must be
  reachable from the API; while it is empty every protected route answers
  `503`.
- **Protonmail Bridge**: SMTP (and IMAP when inbound processing is enabled),
  if the `protonmail` provider is used.
- **The applications' callback endpoints**: the worker posts the
  [status callbacks](20-status-callbacks.md) to the URLs of the clients.

## Database migrations

Run the migrations on every deployment, before restarting the processes:

```bash
alembic -c apps/mailler/alembic.ini upgrade head
```

Revisions `001` to `009` correspond to the [sending](04-send.md),
[templates](08-templates.md), [contacts](09-contacts.md),
[campaigns](12-campaigns.md) and [inbound](14-inbound.md) features, then to
the [client registry](15-authorized-clients.md), the
[limits](16-client-limits.md), the [idempotency key](19-idempotency.md) and
the [callbacks](20-status-callbacks.md). They are written for PostgreSQL and
were not run against a database in the test suites of this repository, which
use SQLite (the steps of `006` to `009` that only add columns, indexes and
constraints are exercised on SQLite).

When the database predates the client registry, set `LEGACY_CLIENT_ID` for the
run of revision `006`: it names the client that owns the data that already
exists, and the migration stops with an explanation if such rows exist and it
is empty.

## Configuration

Settings are environment variables (each feature page has its own table). The
defaults describe no deployment: nothing is sent and nobody is trusted until
the following are set.

| Variable | Why it has to be set |
| --- | --- |
| `DATABASE_URL`, `REDIS_URL`, `CELERY_BROKER_URL`, `CELERY_RESULT_BACKEND` | Local development URLs by default |
| `OAUTH2_ISSUER`, `OAUTH2_CLIENT_ID`, `OAUTH2_CLIENT_SECRET` | Empty issuer: every protected route answers `503` |
| `ADMIN_SCOPE` | Scope of the operators (default `mailler:admin`) |
| `CORS_ORIGINS` | Empty: no browser origin is allowed |
| `UNSUBSCRIBE_BASE_URL` | Public base URL of the API, to build the unsubscribe links of campaigns |
| `LEGACY_CLIENT_ID` | Only to migrate a database created before the registry |
| `PROTONMAIL_HOST`, `PROTONMAIL_PORT`, `PROTONMAIL_USER`, `SES_REGION` | A provider is only available when its settings are complete |
| `INBOUND_IMAP_PORT`, `INBOUND_ATTACHMENTS_DIR`, `INBOUND_WEBHOOK_URL` | Required when `INBOUND_ENABLED` is true |
| `DEFAULT_FROM`, `DEFAULT_FROM_NAME`, `DEFAULT_PROVIDER` | Optional, only for administrators without a client record |

Tunables with their defaults are on the feature pages: delivery retries
([sending](04-send.md)), scheduler thresholds and retention
([scheduling](07-schedule.md)), campaign batches ([campaigns](12-campaigns.md)),
the registry cache ([authorized clients](15-authorized-clients.md)) and the
callback delivery ([callbacks](20-status-callbacks.md)).

The API process needs all of them; the worker needs the Celery URLs,
`DATABASE_URL`, the provider settings, `WEBHOOK_HMAC_SECRET` and the callback
settings; beat needs the Celery URLs. `INBOUND_ENABLED` and the other inbound
settings must be identical on the API, worker and beat processes.

### Secrets

Secrets are supplied as systemd credentials (a file named after the variable
in `CREDENTIALS_DIRECTORY`) or, failing that, as environment variables. Never
write them to a `.env` file under version control.

| Secret | Used by |
| --- | --- |
| `OAUTH2_CLIENT_SECRET` | API (introspection and token exchange) |
| `WEBHOOK_HMAC_SECRET` | API (webhooks, unsubscribe) and worker (signing outgoing messages) |
| `BREVO_API_KEY`, `SENDGRID_API_KEY` | Worker (sending) and API (Brevo contact unblock) |
| `SES_ACCESS_KEY`, `SES_SECRET_KEY` | Worker |
| `PROTONMAIL_PASSWORD` | Worker, and the inbound poller |
| `INBOUND_WEBHOOK_SECRET` | Worker (inbound forwarding) |

The secrets that sign the callbacks of each client are not environment
variables: they are stored in the `authorized_clients` table, so the database
and its backups are as sensitive as the secrets above.

## Operations

- Scale the API through the number of gunicorn workers and the worker through
  its concurrency; keep a single beat.
- Tasks are acknowledged late and rejected back to the queue if a worker dies,
  with a 300 second hard limit, so a restart never loses an email in flight.
- The `provider_stats` rows and the `emails` table are the only sources of
  sending history; `cleanup_old_emails` removes emails after
  `EMAIL_RETENTION_DAYS` days, together with their idempotency keys.
- Deactivating a client (`mailler clients deactivate`) takes effect within
  `CLIENT_CACHE_TTL` seconds on every API process and stops its queued emails.
- Back up the `mailler` database; the inbound attachment directory only holds
  short-lived copies.
