# Deployment

How `auth` runs in production. The production inventory and its secrets are
kept outside this repository, in the Ansible inventory that consumes the
`goabonga.website` collection; this page lists the processes, the settings and
the secrets they need, without any value. One code base is deployed as three
processes: the web API, a Celery worker and the Celery beat scheduler.

## Processes

| Process | Command | Notes |
| --- | --- | --- |
| Web API | `gunicorn auth.main:app` with the `uvicorn.workers.UvicornWorker` class, two workers, on a Unix socket | behind nginx; `/health` is the probe endpoint |
| Worker | `celery -A auth.celery:celery_app worker -Q auth` (concurrency 2) | sends e-mails, delivers webhooks, runs the cleanup tasks and provisions custom domains |
| Beat | `celery -A auth.celery:celery_app beat` | schedules the periodic jobs of the [maintenance](15-maintenance.md) and [webhook](05-webhooks.md) features; run exactly one instance |

Gunicorn and uvicorn are installed by the deployment, next to the package
(they are declared in `apps/auth/pyproject.toml`). Older deployments referenced
the code as `app.main:app` and `app.celery:celery_app`; from this repository the
import package is `auth`, so the units must use the new paths.

The three processes run as the same dedicated system user. The user belongs to
the group of the `mailler` service so that it can reach its Unix socket when
`EMAIL_BACKEND=mailler`.

## Reverse proxy and tenants

nginx terminates TLS and proxies to the socket. Because organisations are
served on sub-domains of `TENANT_BASE_DOMAIN`, the certificate must cover the
wildcard `*.<base domain>`; that requires a DNS-01 challenge with a DNS
provider the certbot setup can use, and a wildcard DNS record pointing to the
host. Organisations with their own domain are handled by the worker, which
writes extra nginx server blocks and runs certbot (see
[Background maintenance](15-maintenance.md)).

Because of that, the worker unit differs from the web unit:

- it may call a short list of privileged commands through `sudo`: the nginx
  configuration test, the nginx reload, `certbot certonly`, and copying or
  removing the `custom-domain-*` server blocks;
- it needs write access to the nginx sites directory, `/etc/letsencrypt`,
  `/var/lib/letsencrypt`, the ACME webroot and the nginx and certbot logs; the
  systemd option `NoNewPrivileges` therefore cannot be enabled for it.

Rate limiting of the sensitive routes is done outside the application, with
fail2ban jails on `POST /auth/register`, `POST /auth/login`,
`POST /oauth2/token` and the password reset route.

## Data stores

- **PostgreSQL**: one database owned by the service user, reached through the
  local socket (`DATABASE_URL=postgresql:///<database>`). Run the migrations on
  every release: `alembic -c apps/auth/alembic.ini upgrade head` (see
  [Data model and migrations](02-data-model.md)). Back the database up: it holds
  the accounts, the sessions and the encrypted signing keys.
- **Redis**: the Celery broker (`CELERY_BROKER_URL`). The result backend stays
  disabled unless `CELERY_RESULT_BACKEND` is set, since the tasks are
  fire-and-forget. Sharing the broker with other applications is safe because
  the `auth` queue is dedicated.
- **Upload directory** (`UPLOAD_DIRECTORY`): avatars, served under `/uploads`.
  Keep it on persistent storage; the cleanup job removes orphaned files.
- **Mailler or SMTP** for outgoing e-mail (see
  [Registration](06-registration.md)).

## Bootstrapping

On a fresh database, after the migrations, create the first signing key and an
administrator with the scripts described in
[Background maintenance](15-maintenance.md):

```bash
python apps/auth/scripts/generate_jwks.py
python apps/auth/scripts/create_user.py --email <address> --verified
python apps/auth/scripts/promote_user.py --email <address> --role super_admin
```

The default roles and scopes are created by the seed actions of the
[administration console](16-admin-ui.md) or `POST /api/v1/roles/seed`. The
scopes and roles of the other services are declared in a catalog file and
applied, after the migrations of every release, with
[`auth catalog sync`](19-catalog.md), which is idempotent.

## Settings in production

The environment file of each unit sets the variables documented on the feature
pages:

| Feature page | Variables |
| --- | --- |
| [Application foundation](01-foundation.md) | `LOG_LEVEL` |
| [Data model and migrations](02-data-model.md) | `DATABASE_URL`, `DATABASE_POOL_SIZE`, `DATABASE_MAX_OVERFLOW`, `DATABASE_ECHO` |
| [Signing keys](03-signing-keys.md) | `JWKS_ENCRYPTION_KEY`, `JWKS_KEY_SIZE`, `JWKS_ROTATION_DAYS`, `JWKS_GRACE_PERIOD_DAYS` |
| [Multi-tenancy](04-tenancy.md) | `ISSUER`, `SESSION_COOKIE_NAME`, `TENANT_BASE_DOMAIN`, `TENANT_CUSTOM_DOMAIN_LOOKUP` |
| [Webhooks](05-webhooks.md) | `CELERY_BROKER_URL`, `CELERY_RESULT_BACKEND`, `WEBHOOK_*` |
| [Registration](06-registration.md) | `EMAIL_BACKEND`, `SMTP_*`, `MAILLER_*`, `VERIFICATION_CODE_EXPIRY_HOURS`, `PASSWORD_RESET_EXPIRY_HOURS`, `TEMPLATES_PATH`, `UPLOAD_*` |
| [Sessions](07-sessions.md) | `SESSION_EXPIRY_DAYS`, `SESSION_COOKIE_SECURE` |
| [Multi-factor authentication](08-mfa.md) | `MFA_ISSUER_NAME`, `MFA_EMAIL_CODE_EXPIRY_MINUTES` |
| [OAuth2 server](10-oauth2-server.md) | `AUTHORIZATION_CODE_EXPIRY_MINUTES`, `ACCESS_TOKEN_EXPIRY_MINUTES`, `REFRESH_TOKEN_EXPIRY_DAYS`, `ID_TOKEN_EXPIRY_MINUTES`, `DEVICE_CODE_EXPIRY_MINUTES`, `DEVICE_CODE_INTERVAL`, `PAR_REQUEST_EXPIRY_SECONDS` |
| [Maintenance](15-maintenance.md) | `CUSTOM_DOMAIN_*`, `UNVERIFIED_USER_EXPIRY_DAYS`, `ORPHAN_AVATAR_CLEANUP_ENABLED` |
| [Catalog](19-catalog.md) | `CATALOG_FILE` |

Set `SESSION_COOKIE_SECURE` to `true` and `ISSUER` to the public HTTPS URL of
the service: the issuer is written into every token and the discovery document.
The worker needs the database, e-mail, Celery and custom domain variables; the
beat scheduler only needs the broker and the database.

### Secrets

Three values are secrets and are never written in the environment file. They
are delivered with systemd credentials (encrypted with `systemd-creds` and
loaded with `LoadCredentialEncrypted`), which the application reads from
`$CREDENTIALS_DIRECTORY` before falling back to the environment:

- `JWKS_ENCRYPTION_KEY`, the base64 AES-256 key that protects the private
  signing keys and the stored client secrets. Losing it makes the stored keys
  unreadable; changing it requires re-encrypting them;
- `SMTP_PASSWORD`;
- `MAILLER_CLIENT_SECRET`.

## Deploying with the Ansible collection

The `goabonga.website` collection of this repository deploys the application
from its catalog (`ansible/roles/python_app/defaults/main/catalog.yml`), which
defines three components built from this monorepo: `auth` (the web API),
`auth_worker` and `auth_beat`. Add `auth` to `website_apps_enabled` and run the
`goabonga.website.apps` playbook, optionally limited with
`-e '{"website_apps_limit": ["auth"]}'`. The collection:

- creates the system user, the PostgreSQL database `auth` and the nginx virtual
  host (with the wildcard certificate for the tenant sub-domains), the
  fail2ban jails and the health check on `/health`;
- installs the package, writes the environment files and the systemd units
  (gunicorn on a socket for `auth`, `celery worker -Q auth` for `auth_worker`,
  `celery beat` for `auth_beat`), with the sudoers entries and writable paths
  of the worker;
- runs `alembic upgrade head` on every deployment of the `auth` component, then
  `auth bootstrap`, `auth catalog sync` and `auth tenant-roles sync`: the
  catalog file is rendered from the `auth_catalog` declared by the catalog entry
  of each enabled application, and the platform tenant and the Swagger UI client
  come from the `website_auth_*` variables (see [Scopes and roles of the platform services](../../ansible/09-auth-catalog.md));
- delivers `JWKS_ENCRYPTION_KEY` and `MAILLER_CLIENT_SECRET` (and the optional
  `SMTP_PASSWORD`) as encrypted systemd credentials, from the `website_secrets`
  of the inventory.

Adjust the catalog from the inventory with `website_apps_overrides`, keyed by
component, for example to send mail through SMTP instead of the mailler
service, or to pin the three components to the same release tag
`auth-vX.Y.Z`:

```yaml
website_apps_overrides:
  auth:
    version: auth-v1.0.0
    env_vars:
      EMAIL_BACKEND: smtp
    secret_names: [JWKS_ENCRYPTION_KEY]
    optional_secret_names: [SMTP_PASSWORD]
  auth_worker:
    version: auth-v1.0.0
    secret_names: [JWKS_ENCRYPTION_KEY]
    optional_secret_names: [SMTP_PASSWORD]
  auth_beat:
    version: auth-v1.0.0
```

Keep the three versions identical so that the code, the migrations and the
Celery tasks stay consistent.

## Local development

`apps/auth/compose.yml` starts a throw-away PostgreSQL 16 (port 5437, database,
user and password `auth`), a Redis 7 (port 6384) and a mail catcher (SMTP on
port 1025, web interface on port 1080):

```bash
docker compose -f apps/auth/compose.yml up -d
export DATABASE_URL=postgresql://auth:auth@localhost:5437/auth
export CELERY_BROKER_URL=redis://localhost:6384/0
export EMAIL_BACKEND=smtp SMTP_HOST=localhost SMTP_PORT=1025 SMTP_TLS=false
export JWKS_ENCRYPTION_KEY=$(python3 -c "import os,base64;print(base64.b64encode(os.urandom(32)).decode())")
uv run --package auth alembic -c apps/auth/alembic.ini upgrade head
uv run --package auth uvicorn auth.main:app --reload --port 8000
```

## Tests

Neither suite needs the compose services:

```bash
uv run --package auth --group dev pytest apps/auth
uv run --package auth --group dev behave apps/auth/features
```

pytest mocks the database, Redis, SMTP and the outbound HTTP calls; behave
replaces them with in-process fakes (an SQLite database that stands in for
PostgreSQL, captured e-mails, `httpx.MockTransport` servers, recorded system
commands). Neither suite has been run against a real PostgreSQL, Redis, nginx
or certbot, so the PostgreSQL-specific parts (the array and JSONB columns and
the partial indexes) are only exercised through the SQLite stand-in.
