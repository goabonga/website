# Deployment

How apt-server runs in production. The production inventory and its secrets
are kept outside this repository; this page lists the process, the settings
and the secrets it needs, without any value.

## Process

A single systemd unit runs `gunicorn apt_server.main:app` with the
`uvicorn.workers.UvicornWorker` class, two workers, listening on a Unix socket
that nginx proxies to. There is no Celery worker and no scheduler: the only
background work is the lazy cleanup of unfinished chunked uploads and the
share notification tasks, both inside the API process.

Gunicorn is a dependency of the package, started from the application
environment by the deployment, but not imported by it.
Older deployments referenced the code as `app.main:app`; from this repository
the import package is `apt_server`, so the path becomes `apt_server.main:app`.

`GET /health` is the probe endpoint, usually restricted to the loopback
addresses in nginx.

## nginx

nginx terminates TLS and needs two things beyond a plain proxy:

- a body size limit large enough for the biggest package, because the
  single-request upload and the chunk endpoints receive the file through
  nginx (`client_max_body_size` of 500 MB matches the default
  `UPLOAD_MAX_SIZE`);
- an `internal` location used by `X-Accel-Redirect`, with the prefix set in
  `APT_INTERNAL_PREFIX` (default `/_internal`) aliased to `APT_REPO_ROOT`, so
  `.deb` files are sent with `sendfile` without crossing Python:

```nginx
location /_internal/ {
    internal;
    alias /var/lib/apt-server/;
    sendfile on;
    tcp_nopush on;
}
```

## Data stores and disk

- **PostgreSQL** reached through the local socket with peer authentication
  (`DATABASE_URL=postgresql:///<database>`, rewritten to the asyncpg driver).
  Run the migrations on every release:
  `alembic -c apps/apt-server/alembic.ini upgrade head`. Back the database up
  regularly: it holds the package metadata and the grants.
- **Redis** is optional and only caches authentication results (token
  introspection, token exchange and UserInfo). Define `REDIS_URL` and a
  dedicated `REDIS_KEY_PREFIX` to enable it; when empty, each authenticated
  call introspects the token. The rendered `Packages` indexes are **not** in
  Redis: they are cached in the `index_cache` table, whose lifetime is
  `APT_INDEX_CACHE_TTL`.
- **Repository directory** `APT_REPO_ROOT` holds `pool/` and the temporary
  `.uploads/` sessions. The service user needs read and write access; with
  systemd hardening (`ProtectSystem=strict`) it must be listed in
  `ReadWritePaths`. nginx only needs read access.
- **GPG key**: the key named by `APT_GPG_KEY_ID` must be in the keyring of the
  service user, since `Release` is signed and exported with `/usr/bin/gpg`.
- **Mailler socket**: for share notifications over `MAILLER_UNIX_SOCKET`, the
  service user must belong to the group that owns the socket.

## Settings in production

The environment file of the unit sets the variables documented on the feature
pages.

| Feature page | Variables |
|--------------|-----------|
| Foundation | `LOG_LEVEL`, `APP_NAME`, `DOCS_ENABLED`, `BACKEND_CORS_ORIGINS`, `FRONTEND_HOST` |
| OIDC authentication | `OAUTH2_ISSUER`, `OAUTH2_CLIENT_ID`, `OAUTH2_SWAGGER_CLIENT_ID`, `OAUTH2_TRUSTED_ISSUERS`, cache TTLs, `REDIS_URL`, `REDIS_KEY_PREFIX` |
| Access control, indexes, endpoints | `APT_SUITES`, `APT_COMPONENTS`, `APT_PUBLIC_COMPONENTS`, `APT_ARCHITECTURES`, `APT_ORIGIN`, `APT_LABEL`, `APT_GPG_KEY_ID`, `APT_INDEX_CACHE_TTL`, `APT_INTERNAL_PREFIX` |
| Catalog and uploads | `DATABASE_URL`, `APT_REPO_ROOT`, `UPLOAD_CHUNK_SIZE`, `UPLOAD_MAX_SIZE`, `UPLOAD_TTL` |
| Web sessions | `SESSION_COOKIE_NAME`, `SESSION_MAX_AGE` |
| Share notifications | `EMAIL_BACKEND`, `MAILLER_*`, `EMAIL_FROM`, `EMAIL_FROM_NAME` |

### Secrets

Four values are secrets and are never written in the environment file. They
are delivered with systemd credentials (encrypted with `systemd-creds`,
loaded with `LoadCredentialEncrypted`), which the application reads from
`$CREDENTIALS_DIRECTORY` before falling back to the environment:

- `OAUTH2_CLIENT_SECRET`
- `SESSION_SECRET`
- `MAILLER_CLIENT_SECRET`
- `WEBHOOK_SECRET` (returned by `auth` when the webhook subscription for the
  user events is registered)

### Registrations at the identity provider

- A confidential client (`OAUTH2_CLIENT_ID`) allowed to call the introspection
  endpoint, and to use token exchange when scopes are checked.
- A public PKCE client (`OAUTH2_SWAGGER_CLIENT_ID`) whose redirect URIs include
  the `/callback` page and `/docs/oauth2-redirect` of the deployment.
- A webhook subscription pointing to `/webhooks/auth` for `user.created`,
  `user.updated`, `user.email_changed`, `user.email_verified` and
  `user.deleted`.
- A client with the `mailler:send` scope for `MAILLER_CLIENT_ID`.

## Ansible

The [python_app](../../ansible/roles/python_app.md) role deploys the unit from
the catalog of the `apps` playbook
([Deploying applications](../../ansible/05-deploying-apps.md)): enable
`apt_server` in `website_apps_enabled` and it brings the single component
`apt_server`, whose unit is named `apt-server`.

- gunicorn listens on the socket `/run/apt-server/apt-server.sock`, with 2
  workers and a `/health` probe. The `apt_server` database is migrated with
  Alembic on each release and reached with the asyncpg driver.
- The nginx virtual host (`apt` entry of `website_hostnames`) sets
  `client_max_body_size 500M` and the `/_internal/` location aliased to
  `/var/lib/apt-server/`, as shown above. That directory is the only extra
  writable path of the unit (`APT_REPO_ROOT`).
- The unit joins the `mailler` group and sends the share notifications through
  `/run/mailler/mailler.sock` (`EMAIL_BACKEND=mailler`, `MAILLER_PROVIDER`
  from `website_mailler_provider`, `MAILLER_AUTH_URL` on the `auth` host), so
  enable `mailler` first. Redis is enabled on database 14 with the key prefix
  `apt_server`.
- The four secrets (`OAUTH2_CLIENT_SECRET`, `SESSION_SECRET`,
  `MAILLER_CLIENT_SECRET`, `WEBHOOK_SECRET`) are required in
  `website_secrets` ([Secrets](../../ansible/03-secrets.md)).
- The catalog does not set `MAILLER_CLIENT_ID`, `APT_GPG_KEY_ID`,
  `FRONTEND_HOST` and `APT_ORIGIN`: add them with `env_vars` in
  `website_apps_overrides`. The GPG key must still be imported in the keyring
  of the service account; nothing in the role does it, and the OAuth2 client
  identifiers come from `website_oauth2_clients`.
