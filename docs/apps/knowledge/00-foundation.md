# Foundation

The foundation is the skeleton every other feature plugs into: an ASGI
application split into a public API and an internal sub-application,
environment-driven settings, structured logging and a health check.

## Application layout

`knowledge.main:app` is the entry point. It is a FastAPI application that:

- exposes the public, customer-facing API (interactive documentation at
  `/docs`, `/redoc` and `/openapi.json`, only when `DOCS_ENABLED` is true);
- applies the CORS middleware configured from the settings;
- mounts the internal sub-application (`knowledge.internal:internal_app`) at
  the root. The sub-application has its own OpenAPI documentation at
  `/internal/docs`, `/internal/redoc` and `/internal/openapi.json`.

The internal sub-application groups the routes that are not part of the
public API. At this stage it only carries the health check; later features
add webhooks, authentication callbacks and the web UI to it.

## Endpoints

| Method | Path | Description |
| --- | --- | --- |
| `GET` | `/health` | Returns `{"status": "healthy", "version": "<version>"}`. Hidden from the OpenAPI schema. |

The health check is what load balancers and the reverse proxy probe. It does
not touch any backing service.

## Settings

Settings are read by `knowledge.config.Settings` (pydantic-settings) from
environment variables, falling back to a `.env` file in the working
directory. Names are case-insensitive.

| Variable | Default | Description |
| --- | --- | --- |
| `APP_NAME` | `Knowledge API` | Display name used in the OpenAPI titles and in log lines. |
| `DEBUG` | `false` | Debug flag. |
| `LOG_LEVEL` | `INFO` | Minimum log level (`DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL`). |
| `DOCS_ENABLED` | `false` | Serves `/docs`, `/redoc` and `/openapi.json` of the public API. |
| `CORS_ORIGINS` | `["*"]` | Allowed origins (JSON list). |
| `CORS_CREDENTIALS` | `true` | Allow credentials on cross-origin requests. |
| `CORS_METHODS` | `["*"]` | Allowed methods (JSON list). |
| `CORS_HEADERS` | `["*"]` | Allowed headers (JSON list). |

Secrets are read with `knowledge.config.get_credential(name)`: when the
process runs under systemd with `LoadCredentialEncrypted`, the value comes
from the file `$CREDENTIALS_DIRECTORY/<name>`; otherwise the environment
variable of the same name is used. Features that need secrets (OpenAI key,
OAuth2 client secret, ...) use this helper when they are introduced.

## Logging

`knowledge.logging.setup_logging` configures two streams: records up to
`INFO` go to stdout, `WARNING` and above go to stderr, so that systemd can
capture them in separate files. Every line carries the request context
(`user=` and `tenant=`), set with `set_request_context`, cleared with
`clear_request_context` and enriched with `log_action`. Noisy third-party
loggers (`urllib3`, `httpx`, `httpcore`) are limited to `WARNING`.

## Running locally

```bash
uv sync --package knowledge
uv run --package knowledge uvicorn knowledge.main:app --reload --port 8003
```

In production the application runs under gunicorn, using
`knowledge.main:app` as module path, and is reached through a reverse proxy
that probes `/health`.

## Tests

pytest (`tests/`):

- `test_health.py`: the health endpoint payload and version.
- `unit/test_config.py`: credential lookup from systemd credentials and the
  environment, settings defaults, environment overrides and caching.
- `unit/test_logging.py`: request context helpers and `log_action`.
- `unit/test_main.py`: lifespan logging, public docs disabled by default,
  internal docs served, health served by the sub-application and CORS
  preflight.

behave (`features/foundation.feature`), driven in-process through httpx:

- Health endpoint reports the service as healthy
- Public interactive documentation is disabled by default
- Internal API documentation is served
- Cross-origin preflight requests are answered
