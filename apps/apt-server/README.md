# apt-server

FastAPI microservice that serves a signed APT repository with per-package
access control.

## Features

- Application foundation: settings from the environment, structured logging,
  `/health` endpoint, optional Swagger UI
- OIDC bearer and personal access token authentication (`/me`)
- Component visibility and `apt:*` scope hierarchy
- Package catalog and per-package ACL stored in PostgreSQL (Alembic)

## Routes and scopes

HTTP routes served by the application and what each one requires. `public` routes need no bearer token or session. A scope is checked on the access token issued by the `auth` application; the wildcards `*` and `<resource>:*` also match.

| Method | Path | Required scope / role / auth | Description |
| --- | --- | --- | --- |
| GET | `/docs` | public | Serve Swagger UI with custom static assets (only when `DOCS_ENABLED` is set) |
| GET | `/docs/oauth2-redirect` | public | OAuth2 redirect page for Swagger UI (only when `DOCS_ENABLED` is set) |
| GET | `/health` | public | Health check endpoint |
| GET | `/me` | bearer token (any scope) | Return current user profile from OIDC UserInfo |

The built web client and other static files are served publicly under `/static`.

## Development

All commands run from the workspace root.

```bash
uv sync --package apt-server --group dev

# Tests (pytest) and feature scenarios (behave) run in-process, no
# external service is needed
uv run --package apt-server --group dev pytest apps/apt-server
uv run --package apt-server --group dev behave apps/apt-server/features

# Serve with reload
uv run --package apt-server uvicorn apt_server.main:app --reload --port 8000
```

Settings are read from environment variables or a `.env` file; see
`.env.example`.
