# apt-server

FastAPI microservice that serves a signed APT repository with per-package
access control.

## Features

- Application foundation: settings from the environment, structured logging,
  `/health` endpoint, optional Swagger UI

## Routes and scopes

HTTP routes served by the application and what each one requires. `public` routes need no bearer token or session.

| Method | Path | Required scope / role / auth | Description |
| --- | --- | --- | --- |
| GET | `/docs` | public | Serve Swagger UI with custom static assets (only when `DOCS_ENABLED` is set) |
| GET | `/docs/oauth2-redirect` | public | OAuth2 redirect page for Swagger UI (only when `DOCS_ENABLED` is set) |
| GET | `/health` | public | Health check endpoint |

The built web client and other static files are served publicly under `/static`.

## Development

All commands run from the workspace root.

```bash
uv sync --package apt-server --group dev

# Serve with reload
uv run --package apt-server uvicorn apt_server.main:app --reload --port 8000
```

Settings are read from environment variables or a `.env` file; see
`.env.example`.
