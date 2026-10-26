# Application foundation

The foundation provides the installable package, the settings object, the
logging setup, the database connection helpers, the FastAPI application
with its health check and a Swagger UI served from local assets. The
following features add the data model, the signing keys, the tenants and
the authentication flows on top of it.

## What it does

- Defines the `auth` package (`auth.__version__`, currently `0.0.0`, managed
  by the release tooling).
- Reads the settings from environment variables into a `Settings` object,
  exposed as the module-level singleton `auth.config.settings`. A `.env`
  file in the working directory is loaded when present. Secrets can also be
  provided as systemd credentials (`get_credential`).
- Configures logging (`auth.core.logging.setup_logging`) before anything
  else, with a log level taken from `LOG_LEVEL`.
- Creates the async SQLAlchemy engine and session factory
  (`auth.core.database`), converting `postgresql://` and `postgres://` URLs
  to the `asyncpg` driver, and exposes a synchronous session helper for
  Celery workers. `auth.db.base` holds the declarative `Base` shared by all
  models.
- Builds the FastAPI application (`auth.main:app`): a custom
  `/docs` Swagger UI that serves its JavaScript and CSS from
  `auth/static/` instead of a CDN (its title and its OAuth2 client come from the
  settings, nothing about a deployment is written in the code), and a JSON error handler for
  `HTTPException` that sends the headers of the exception (a redirect keeps its
  `Location`, a 401 its `WWW-Authenticate`). A 403 raised for a browser request
  (`Accept: text/html`) renders the `errors/403.html` template instead.
- Provides the `auth.api.deps.get_db` dependency that yields a session,
  commits on success and rolls back on error. More dependencies are added to
  this module by the features that need them.

## Endpoints

### `OpenAPI document (FastAPI)`

| Method | Path | Handler | Summary |
| --- | --- | --- | --- |
| GET | `/openapi.json` | `openapi` |  |

### `auth.main`

| Method | Path | Handler | Summary |
| --- | --- | --- | --- |
| GET | `/docs` | `custom_swagger_ui` | Serve Swagger UI with local static assets (no external CDN dependency). |
| GET | `/docs/oauth2-redirect` | `swagger_ui_redirect` | OAuth2 redirect page for Swagger UI. |

### `health`

| Method | Path | Handler | Summary |
| --- | --- | --- | --- |
| GET | `/health` | `health` | Return a liveness signal for load balancers and container probes. |

`/health` is deliberately dependency free: it performs no database or cache
I/O, so it stays responsive during a partial outage. Swagger UI and the
OpenAPI document are not part of the OpenAPI schema themselves.

## Settings

| Variable | Default | Description |
| --- | --- | --- |
| `LOG_LEVEL` | `INFO` | DEBUG, INFO, WARNING, ERROR, CRITICAL |
| `DATABASE_URL` | `postgresql://localhost:5432/auth` | SQLAlchemy URL; `postgresql://`, `postgres://` and `postgresql+asyncpg://` are accepted |
| `DATABASE_POOL_SIZE` | `5` | Connections kept in the pool |
| `DATABASE_MAX_OVERFLOW` | `10` | Extra connections allowed beyond the pool size |
| `DATABASE_ECHO` | `False` | Log every SQL statement |
| `APP_TITLE` | `OIDC/OAuth2 Service` | Title of the OpenAPI document and of the `/docs` page |
| `SWAGGER_CLIENT_ID` | `swagger-ui` | `client_id` that the Swagger UI "Authorize" button sends (the OAuth2 client of the same id must exist in the deployment) |
| `SWAGGER_SCOPES` | `openid profile email` | Space-separated scopes that Swagger UI requests (a deployment that wants the admin API in `/docs` adds `*`) |

Settings are read once, when `auth.config` is imported. Later features add
their own variables to the same object.

## Data model

None yet. The connection helpers exist, the tables arrive with the next
feature.

## Running it

```bash
uv sync --package auth
uv run --package auth uvicorn auth.main:app --reload --port 8000
curl http://127.0.0.1:8000/health
# {"status":"healthy"}
```

In production the application is served by gunicorn with uvicorn workers,
see the deployment page. `gunicorn` and `uvicorn` are declared as
dependencies for that purpose.

## Tests

- pytest: 7 new test modules.
  New modules: `tests/test_api_deps.py`, `tests/test_config.py`, `tests/test_database.py`, `tests/test_db_base.py`, `tests/test_logging.py`, `tests/test_main.py`, `tests/test_routes_health.py`.
- behave: `features/foundation.feature` with the scenarios *The health probe reports a live process*, *Swagger UI is served from local assets*, *Unknown paths return a JSON error*, *Settings fall back to their defaults*, *Settings are overridden by the environment*, *The title and the Swagger UI client come from the environment*, *The database URL is converted for the asyncpg driver*.

### Browser scenarios

`features/browser/foundation.feature` is tagged `@browser`: its 4 scenarios drive the
application in Chromium (see [browser tests](../../testing/index.md)).

- Swagger UI renders the API from local assets only
- The health probe answers in the browser
- The favicon is served as an image
- An unknown path shows a JSON error

The scenarios open the documentation page and the probes in Chromium, record every request the page makes to prove that nothing leaves the application, and fetch the favicon.
