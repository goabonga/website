# Deployment

How the analytics service runs in production. The production inventory and its
secrets are kept outside this repository: this page lists the process, the
data stores, the settings and the secrets, without any value. The
`analytics.example.com` host name below is a placeholder.

## Process

The service is one systemd unit running as its own Unix user.

| Item | Value |
| --- | --- |
| Command | `gunicorn analytics.main:app` with `uvicorn.workers.UvicornWorker` |
| Workers | 2 |
| Listener | Unix socket, proxied by nginx |
| Health probe | `GET /health` |
| Public host | one dedicated host name, TLS terminated by nginx |

There is no Celery worker and no scheduler: all work happens in the request.

Older deployments referenced the code as `app.main:app`; from this repository
the import package is `analytics`, so the module path becomes
`analytics.main:app`.

nginx terminates TLS and proxies to the gunicorn socket. The application trusts
the first address of `X-Forwarded-For` as the client IP (see the collection
page): nginx must set that header and the socket must not be reachable any
other way, otherwise visitors can forge their IP address.

## Data stores

- **PostgreSQL**, one database for the service, reached through the local
  socket with peer authentication (`DATABASE_URL=postgresql:///analytics`).
  Run the migrations on every release:
  `alembic -c apps/analytics/alembic.ini upgrade head`. Databases created by
  the original single `001` revision are upgraded in place: revisions `002`
  and `003` skip the tables that already exist.
- **Redis**, one logical database, reached through its Unix socket or TCP
  (`REDIS_URL`), used by the token introspection and token exchange caches.
  If Redis is down the caches are skipped with a warning.
- **GeoIP database**: a MaxMind `GeoLite2-City.mmdb` file readable by the
  service user. Without it geolocation is switched off.

## Settings in production

The environment file of the unit sets the variables documented on the feature
pages.

| Feature page | Variables |
| --- | --- |
| Foundation | `LOG_LEVEL`, `APP_NAME`, `DOCS_ENABLED`, `CORS_ORIGINS` |
| security.txt | `SECURITY_CONTACT`, `SECURITY_EXPIRES`, `SECURITY_PREFERRED_LANGUAGES`, ... |
| Storage | `DATABASE_URL`, `DATABASE_ECHO`, `DATA_RETENTION_DAYS` |
| Enrichment | `GEOIP_ENABLED`, `GEOIP_DATABASE_PATH` |
| Collection | `SESSION_COOKIE_NAME`, `SESSION_COOKIE_MAX_AGE`, `SESSION_COOKIE_SECURE`, `SESSION_COOKIE_SAMESITE`, `SESSION_COOKIE_DOMAIN`, `PIXEL_CACHE_CONTROL`, `ANONYMIZE_IP` |
| Authentication | `OAUTH2_ISSUER`, `OAUTH2_SWAGGER_CLIENT_ID`, `OAUTH2_CLIENT_ID`, `TOKEN_INTROSPECTION_CACHE_TTL`, `OAUTH2_CLIENT_CACHE_TTL`, `REDIS_URL` |

For a site on several sub-domains, set `SESSION_COOKIE_DOMAIN` to the parent
domain (for example `.example.com`) so the session cookie is shared, keep
`SESSION_COOKIE_SECURE=true` and `SESSION_COOKIE_SAMESITE=none` for cross-site
requests, and list the websites that send events in `CORS_ORIGINS`.

Two settings are declared but have no effect today: `CACHE_TTL` and
`DATA_RETENTION_DAYS` (there is no purge job; use the reset route or a
database job to enforce a retention policy).

### Secret

One value is a secret and is not written in the environment file:
`OAUTH2_CLIENT_SECRET`. It is delivered with a systemd credential (encrypted
with `systemd-creds` and loaded with `LoadCredentialEncrypted`), which the
application reads from `$CREDENTIALS_DIRECTORY` before falling back to the
environment.

## Ansible

The [python_app](../../ansible/roles/python_app.md) role deploys the unit from
the catalog of the `apps` playbook
([Deploying applications](../../ansible/05-deploying-apps.md)): enable
`analytics` in `website_apps_enabled` and it brings the single component
`analytics`.

- gunicorn listens on the socket `/run/analytics/analytics.sock`, with 2
  workers, a `/health` probe, an nginx virtual host on the `analytics` entry
  of `website_hostnames`, a `analytics` database and the Alembic migrations on
  each release.
- The environment file sets `REDIS_URL` (database 7), the session cookie
  (`ua_sid`, secure, `SameSite=None`), `DATA_RETENTION_DAYS=395`,
  `ANONYMIZE_IP=false`, `DOCS_ENABLED=false` and the cache lifetimes. It
  enables GeoIP with `/usr/share/GeoIP/GeoLite2-City.mmdb`, the file installed
  by the [geoip](../../ansible/roles/geoip.md) role. `CORS_ORIGINS` lists the
  front end and the API hosts; add the other websites with `env_vars` in
  `website_apps_overrides`, which is also where `SESSION_COOKIE_DOMAIN` is set.
- `OAUTH2_CLIENT_SECRET` is the only secret and is optional: it is deployed
  when set in `website_secrets` ([Secrets](../../ansible/03-secrets.md)).

## Verifying a deployment

```bash
curl -fsS https://analytics.example.com/health
curl -fsS https://analytics.example.com/.well-known/security.txt
curl -fsS -o /dev/null -w '%{content_type}\n' "https://analytics.example.com/collect?t=pageview"
systemctl status analytics
```
