# Deployment

`frontend` is deployed as a single gunicorn process behind nginx. It needs no
database, no Redis and no background worker, and it provisions no secret.
This page lists what the deployment has to provide; the deployment itself is
driven by the Ansible collection of this repository, which is documented in
the Ansible section of the site.

## Process

| Item | Value |
|------|-------|
| Python module | `frontend.main:app` |
| Server | gunicorn with the Uvicorn worker class (`uvicorn.workers.UvicornWorker`) |
| Workers | 2 |
| Listener | Unix socket (the service has a runtime directory for it) |
| Health check | `GET /health` must answer `200` through the socket before the unit counts as started |
| Logs | stdout (`INFO`) and stderr (`WARNING` and above) captured separately by systemd, see [Logging](02-logging.md) |

`gunicorn` and `uvicorn` are dependencies of the package for this purpose.

## Environment

The environment file is written with mode `0600` and read by the application
(directly from the process environment, or as `.env` in its working
directory). Every variable is documented on its feature page:

- [Foundation](01-foundation.md): `APP_NAME`, `DEBUG`, `DOCS_ENABLED`, `CORS_*`
- [Logging](02-logging.md): `LOG_LEVEL`
- [SPA serving](04-spa-serving.md): `STATIC_DIR`, `AUTH_URL`, `API_URL`,
  `ANALYTICS_URL`, `OAUTH2_CLIENT_ID`, `LEGAL_*`, `WELCOME_*`, `SOCIAL_*`
- [security.txt](05-security-txt.md): `SECURITY_*`
- [Server-side analytics](06-analytics.md): `ANALYTICS_URL`

`OAUTH2_CLIENT_ID` is the identifier of a public PKCE client registered on the
authentication server, with the callback URL `/auth/callback` of the site as
redirect URI. It is public by design and needs no vault. The only credential
involved in a deployment is the token used to clone the repository.

## Client build

The deployment must run the web client build on every release, as the service
user, before restarting the service:

```bash
npm --prefix apps/frontend/web ci
npm --prefix apps/frontend/web run build
```

It needs Node.js 20 and writes `apps/frontend/web/dist`. The committed template
means the server starts even without the build, but the page would then have no
scripts or styles (see [Web client](03-web-client.md)).

## nginx

- TLS termination for the public domain, with the `www` host redirected to it.
- `location /static` served directly from the build directory
  (`apps/frontend/web/dist`) and never forwarded to gunicorn, which is why
  static requests are not tracked.
- Every other path proxied to the socket with `X-Real-IP`, `X-Forwarded-For`
  and `X-Forwarded-Proto`, which the analytics middleware relies on.
- `/health` restricted to loopback.

Note on caching: the Vite configuration emits `assets/index.js` and
`assets/index.css` without content hashes, so a long `immutable` cache policy
on `/static` would keep stale assets in browsers after a release. Use a short
lifetime or revalidation unless the file names are changed.

## Differences with the legacy deployment

The catalog entry used before this repository (standalone repository, checkout
in `app/`) must be adapted to the monorepo layout:

| Legacy | Now |
|--------|-----|
| module `app.main:app` | `frontend.main:app` |
| `npm install` and `npm run build` at the repository root | in `apps/frontend/web` |
| static files in `<checkout>/dist` | `apps/frontend/web/dist` (or set `STATIC_DIR`) |
| template generated into `app/templates` | `apps/frontend/src/frontend/templates` |

## Operations

```bash
curl -so /dev/null -w "%{http_code}\n" https://<site>/health   # from loopback only
systemctl status frontend
```

Renew `SECURITY_EXPIRES` before its date, and keep the analytics, auth and API
base URLs aligned with the other applications of the platform.
