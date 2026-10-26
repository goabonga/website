# analytics

Analytics tracking service for goabonga.com.

This is a member of the `website` uv workspace. All commands are run from the
repository root.

## Routes and scopes

HTTP routes served by the application and what each one requires. `public` routes need no bearer token or session. A scope is checked on the access token issued by the `auth` application; the wildcards `*` and `<resource>:*` also match.

| Method | Path | Required scope / role / auth | Description |
| --- | --- | --- | --- |
| GET | `/health` | public | Health check endpoint for monitoring and load balancer probes |
| GET | `/.well-known/security.txt` | public | Return security.txt content (RFC 9116) |
| POST | `/collect` | public | Collect analytics events |
| GET | `/collect` | public | Lightweight GET endpoint for beacon/pixel tracking |
| GET | `/p/{pixel_key}.gif` | public | Track email open via tracking pixel |
| GET | `/p/{pixel_key}` | public | Track pixel without .gif extension (fallback) |
| GET | `/t/{tracking_key}` | public | Track campaign link click and redirect |
| GET | `/api/v1/stats/overview` | scope `analytics:read` | Get overview statistics for the analytics dashboard |
| GET | `/api/v1/stats/daily` | scope `analytics:read` | Get daily statistics for the analytics dashboard |
| GET | `/api/v1/stats/countries` | scope `analytics:read` | Get statistics by country |
| GET | `/api/v1/stats/devices` | scope `analytics:read` | Get statistics by device type |
| GET | `/api/v1/stats/browsers` | scope `analytics:read` | Get statistics by browser |
| GET | `/api/v1/stats/referrers` | scope `analytics:read` | Get statistics by referrer |
| GET | `/api/v1/stats/pages` | scope `analytics:read` | Get statistics by page |
| GET | `/api/v1/stats/events` | scope `analytics:read` | Get statistics by event type |

Swagger UI (`/docs`), ReDoc (`/redoc`) and `/openapi.json` are served only when `DOCS_ENABLED` is true.

### Scopes

The application defines no scope, it only checks the ones carried by the access tokens issued by the `auth` application, which grants them through its catalog of scopes and roles.

- `analytics:read` - checked by 8 routes

## Run

```bash
uv sync --package analytics
uv run --package analytics uvicorn analytics.main:app --reload --port 8000
```

Settings are read from the environment and from a `.env` file in the working
directory; see `.env.example`.

## Features

- Settings, logging, FastAPI application and the `/health` endpoint.
- `/.well-known/security.txt` (RFC 9116).
- PostgreSQL storage for sessions and events (SQLAlchemy models, Alembic revision `001`).
- User agent parsing and optional MaxMind GeoIP lookups.
- Event collection: `POST /collect` and the `GET /collect` beacon with session cookies.
- Campaigns and email tracking pixels (`/p/{key}.gif`, Alembic revision `002`).
- Campaign link redirects with click tracking (`/t/{key}`).
- OAuth2/OIDC bearer authentication with scope checks (token introspection, token exchange).
- Secured traffic statistics under `/api/v1/stats`.

Each feature has a page in `docs/apps/analytics/`.

## Tests

```bash
uv run --package analytics --group dev pytest apps/analytics
uv run --package analytics --group dev behave apps/analytics/features
```
