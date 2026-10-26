# Application foundation

The foundation provides the package skeleton every other feature builds on:
settings, logging, the ASGI application and a health endpoint.

## What it does

- `apt_server.main:app` is the FastAPI application. It is served in
  production by gunicorn with uvicorn workers, and locally by
  `uvicorn apt_server.main:app --reload`.
- `GET /health` returns `{"status": "ok"}`. It is hidden from the OpenAPI
  schema and is meant for load balancer and monitoring probes.
- `/static` serves the favicon and the Swagger UI assets bundled in the
  package, so the API documentation works without a CDN.
- CORS is configured from the settings below.
- Swagger UI is served at `/docs` only when `DOCS_ENABLED=true`. The page uses
  the local assets under `/static` and the OAuth2 redirect page at
  `/docs/oauth2-redirect`.
- Logs go to two streams: records up to `INFO` on stdout, `WARNING` and above
  on stderr. Each line carries the `user` and `client` of the current request
  context (`-` when unset).

## Settings

Settings are read from environment variables or a `.env` file in the working
directory (`apps/apt-server/.env.example` lists them). Names are case
insensitive.

| Variable | Default | Description |
| --- | --- | --- |
| `APP_NAME` | `apt-server` | Application title (OpenAPI and logs) |
| `LOG_LEVEL` | `INFO` | Logging level; unknown values fall back to `INFO` |
| `DOCS_ENABLED` | `false` | Expose Swagger UI at `/docs` |
| `BACKEND_CORS_ORIGINS` | empty | Allowed origins, comma separated or a JSON array |
| `FRONTEND_HOST` | empty | One more origin appended to the CORS list |

Trailing slashes are stripped from CORS origins so they match the browser
`Origin` header.

## Layout

| Path | Role |
| --- | --- |
| `src/apt_server/main.py` | Application, middleware, static files, `/health` |
| `src/apt_server/config.py` | `pydantic-settings` configuration |
| `src/apt_server/logging.py` | Dual-stream logging and request context |
| `src/apt_server/static/` | Favicon and Swagger UI assets |

## Dependencies

`fastapi` and `pydantic-settings` are imported by the code. `uvicorn` and
`gunicorn` are the runtime servers and are not imported by the application.
Test tooling (pytest, behave, httpx) comes from the root `dev` dependency
group of the workspace.

## Tests

Run from the workspace root:

```bash
uv run --package apt-server --group dev pytest apps/apt-server
uv run --package apt-server --group dev behave apps/apt-server/features
```

- pytest: `tests/test_health.py` (health, OpenAPI, static files, Swagger UI
  with and without `DOCS_ENABLED`), `tests/test_config.py` (defaults, CORS
  parsing and merging, environment overrides, `.env.example` consistency) and
  `tests/test_logging.py` (stream filters, request context, handler setup).
- behave: `features/foundation.feature` with the scenarios "Health check
  reports the service is up", "Static assets are served", "Swagger UI is
  disabled by default", "Unknown routes return not found" and "Default
  configuration is applied". Scenarios run in-process through the ASGI
  application, no network or external service is involved.
