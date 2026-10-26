# analytics

Analytics tracking service for goabonga.com.

This is a member of the `website` uv workspace. All commands are run from the
repository root.

## Routes and scopes

HTTP routes served by the application and what each one requires. `public` routes need no bearer token or session.

| Method | Path | Required scope / role / auth | Description |
| --- | --- | --- | --- |
| GET | `/health` | public | Health check endpoint for monitoring and load balancer probes |
| GET | `/.well-known/security.txt` | public | Return security.txt content (RFC 9116) |
| POST | `/collect` | public | Collect analytics events |
| GET | `/collect` | public | Lightweight GET endpoint for beacon/pixel tracking |
| GET | `/p/{pixel_key}.gif` | public | Track email open via tracking pixel |
| GET | `/p/{pixel_key}` | public | Track pixel without .gif extension (fallback) |
| GET | `/t/{tracking_key}` | public | Track campaign link click and redirect |

Swagger UI (`/docs`), ReDoc (`/redoc`) and `/openapi.json` are served only when `DOCS_ENABLED` is true.

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

Each feature has a page in `docs/apps/analytics/`.

## Tests

```bash
uv run --package analytics --group dev pytest apps/analytics
uv run --package analytics --group dev behave apps/analytics/features
```
