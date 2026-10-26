# Application foundation

The foundation provides the installable package, the settings object, the
logging setup and the FastAPI application with its health check. The
following features add authentication, the database, certificate issuance
and the OpenVPN integration on top of it.

## What it does

- Defines the `vpn_portal` package (`vpn_portal.__version__`, currently
  `0.0.0`, managed by the release tooling).
- Reads the settings from environment variables into a `Settings` object,
  exposed as the module-level singleton `vpn_portal.config.settings`. A
  `.env` file in the working directory is read as well; real environment
  variables win over it.
- Configures logging when `vpn_portal.main` is imported: records up to
  `INFO` go to stdout, records at `WARNING` and above go to stderr. Every
  line carries the `user` and `client` of the current request context
  (`-` when there is none), which later features fill from the access token.
  `log_action()` logs a structured `ACTION: ...` line.
- Builds the FastAPI application `vpn_portal.main:app` with a lifespan
  handler that logs start and stop. Swagger UI, ReDoc and `openapi.json`
  are served unless `DOCS_ENABLED=false`.

## Endpoints

| Endpoint | Method | Description |
| --- | --- | --- |
| `/health` | GET | Returns `{"status": "healthy"}`; hidden from the OpenAPI schema |
| `/docs`, `/redoc`, `/openapi.json` | GET | API documentation, only when `DOCS_ENABLED=true` |

## Settings

| Variable | Default | Description |
| --- | --- | --- |
| `APP_NAME` | `VPN Portal` | Application title shown in the API documentation |
| `DEBUG` | `false` | Debug flag |
| `DOCS_ENABLED` | `true` | Serve Swagger UI, ReDoc and the OpenAPI schema |
| `LOG_LEVEL` | `INFO` | Python logging level name; an unknown name falls back to `INFO` |

Settings are read once, when `vpn_portal.config` is imported.

## Data model

None. The application has no database at this stage.

## Running it

```bash
uv sync --package vpn-portal
uv run --package vpn-portal uvicorn vpn_portal.main:app --port 8000
curl http://127.0.0.1:8000/health
```

## Tests

- pytest: `tests/test_config.py` (defaults, environment overrides, `.env`
  file, precedence), `tests/test_health.py` (health endpoint, OpenAPI
  schema, documentation routes, application metadata) and
  `tests/test_logging.py` (stdout/stderr split, levels, request context,
  `log_action`).
- behave: `features/foundation.feature` with the scenarios *Application
  reports healthy status*, *API documentation is served*, *Default
  settings*, *Settings overridden by the environment* and *Logging is split
  between stdout and stderr*.
