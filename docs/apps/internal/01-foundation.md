# Application foundation

The foundation is the smallest runnable application: a FastAPI app factory with
settings, structured logging, CORS and a health endpoint. Every later feature
plugs routers and settings into it.

The settings object lives in `internal.config` and is created once at import
time. Secrets (`SECRET_KEY`, and later the OAuth2 client secret and API keys) are
looked up first in the systemd credentials directory (`$CREDENTIALS_DIRECTORY`,
one file per secret) and then in the environment, so the same code runs under
`LoadCredentialEncrypted` in production and with plain environment variables in
development.

## What it adds

| Module | Role |
| --- | --- |
| `internal/__init__.py` | Internal admin dashboard. |
| `internal/config.py` | Application configuration. |
| `internal/logging.py` | Structured logging configuration with dual output streams. |
| `internal/main.py` | FastAPI main application. |

## Endpoints

| Method | Path | Required scope | Description |
| --- | --- | --- | --- |
| GET | /health | none | Liveness probe; returns `{"status": "healthy"}`. |

## Logging

`internal.logging.setup_logging` configures the root logger with two handlers so
that systemd can split the streams: records below `WARNING` go to stdout, `WARNING`
and above go to stderr. Every line carries the request context:

```text
2026-01-01 12:00:00 | INFO     | user=<id> | client=<id> | internal.routes.x | message
```

`set_request_context`, `clear_request_context` and `log_action` fill the `user` and
`client` fields (they default to `-`). `urllib3`, `httpx` and `httpcore` are
capped at `WARNING` to keep third-party noise out of the logs.

## API documentation

The application metadata (title from `APP_NAME`, version from
`internal.__version__`) is always set, but the interactive documentation
(`/docs`, `/redoc`, `/openapi.json`) is only mounted when `DOCS_ENABLED=true`. It
is off by default so the service does not publish its own surface.

## CORS

`CORSMiddleware` is configured from the four `CORS_*` settings. The list-valued
ones are parsed from JSON, for example `CORS_ORIGINS='["https://admin.example.com"]'`.

## Settings

Read from environment variables (or a `.env` file) by `internal.config.Settings`.

| Variable | Default | Notes |
| --- | --- | --- |
| `APP_NAME` | `'GOABONGA API'` | Application |
| `DEBUG` | `False` | Application |
| `LOG_LEVEL` | `'INFO'` | Application |
| `DOCS_ENABLED` | `False` | Application |
| `CORS_ORIGINS` | `['*']` | CORS |
| `CORS_CREDENTIALS` | `True` | CORS |
| `CORS_METHODS` | `['*']` | CORS |
| `CORS_HEADERS` | `['*']` | CORS |
| `SECRET_KEY` | `'change-me-in-production'` | Session signing key (read from systemd credentials in production) |

## Tests

pytest:

- `tests/test_config.py`
- `tests/test_logging.py`
- `tests/test_main.py`

The tests cover `get_credential` (systemd credential file, environment fallback, default), every logging filter and helper, and the health route.

Behave scenarios, run in-process with `uv run --package internal behave apps/internal/features` (`features/health.feature`):

- Health endpoint reports the service as healthy
- Health endpoint is hidden from the API schema
- Interactive API documentation is disabled by default
- Unknown paths return not found

The behave environment created here is reused and extended by every later feature; `steps/common_steps.py` holds the generic request and response steps.
