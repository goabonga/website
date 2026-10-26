# Running and deployment

This page covers how the service is run locally and how the
`goabonga.website` Ansible collection deploys it.

## Local development

```bash
uv sync --package reachy-mini-api
uv run --package reachy-mini-api uvicorn reachy_mini_api.main:app --reload --port 8002

# tests (no network, no infrastructure)
uv run --package reachy-mini-api pytest apps/reachy-mini-api
uv run --package reachy-mini-api behave apps/reachy-mini-api/features

# lint
uv run ruff check apps/reachy-mini-api
uv run ruff format --check apps/reachy-mini-api
```

Without `OAUTH2_ISSUER`, authenticated `/api` requests answer 503 while `/health`
and `/ws` work. Set `DOCS_ENABLED=true` to browse `/docs`. A `.env` file in the working
directory is loaded, and it must contain only variables the settings know:
pydantic-settings rejects unknown keys in a `.env` file.

`gunicorn` and `uvicorn[standard]` are the servers that run
`reachy_mini_api.main:app`; the code itself does not import `gunicorn`.

## Components

A single web process. There is no worker, no beat scheduler and no Postgres.
Redis is optional and only used as a cache for the
[introspection](07-introspection.md) and the
[token exchange](08-token-exchange.md). The service must run with **one**
gunicorn worker because the WebSocket connections are kept in the memory of
the process ([WebSocket channel](06-websocket.md)).

## Deployment

The application is deployed under the catalog key `reachy_mini_api`:

- type `gunicorn`, module `reachy_mini_api.main:app`, one worker using
  `uvicorn.workers.UvicornWorker`, bound to a Unix socket behind nginx,
- an internal-only nginx virtual host on an `.internal` host name, with a
  certificate issued by the internal Step-CA, listening on the VPN address
  and the loopback only, and restricted by `allow`/`deny` to the VPN range
  (`10.0.0.0/8`) and the local LAN (`192.168.1.0/24`); this is the only access
  control of `/health` and `/ws`,
- `/ws` proxied with the WebSocket upgrade headers and a one hour timeout,
- a health check on `/health`, used before the service is declared ready,
- a hardened systemd unit, and an environment file (mode `0600`) with the
  variables below,
- `OAUTH2_CLIENT_SECRET` delivered as an encrypted systemd credential: the
  unit loads it with `LoadCredentialEncrypted=` and the settings read it from
  `$CREDENTIALS_DIRECTORY`, so it never appears in the environment file.

| Variable | Typical value | Page |
| --- | --- | --- |
| `APP_NAME`, `DEBUG`, `LOG_LEVEL` | `Reachy Mini API`, `false`, `INFO` | [foundation](01-foundation.md), [logging](02-logging.md) |
| `CORS_ORIGINS` | the HTTPS origin of the internal host, as JSON | [foundation](01-foundation.md) |
| `OAUTH2_ISSUER`, `OAUTH2_SWAGGER_CLIENT_ID`, `JWKS_CACHE_TTL` | issuer URL of the auth service, public PKCE client, `3600` | [JWT authentication](03-jwt-auth.md) |
| `OAUTH2_CLIENT_ID`, `TOKEN_INTROSPECTION_CACHE_TTL`, `REDIS_URL` | confidential client, `60`, Redis URL with its database | [introspection](07-introspection.md) |
| `OAUTH2_CLIENT_CACHE_TTL` | `300` | [token exchange](08-token-exchange.md) |

The Redis URL is passed as `REDIS_URL`. The service has no database and no
migration, so no database backup job is needed.

Systemd captures the two logging streams described in
[Dual-stream logging](02-logging.md) in separate files (`output.log` and
`error.log`).

## Dependencies on other applications

The auth service is required: it is the OIDC issuer that publishes the
signing keys, the introspection endpoint and the token exchange endpoint. Its
OAuth2 client for this service must be registered beforehand with the
authorization code, refresh token and token exchange grants. No other
application calls this service.
