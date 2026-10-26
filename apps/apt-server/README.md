# apt-server

FastAPI microservice that serves a signed APT repository with per-package
access control.

## Features

- Application foundation: settings from the environment, structured logging,
  `/health` endpoint, optional Swagger UI
- OIDC bearer and personal access token authentication (`/me`)
- Component visibility and `apt:*` scope hierarchy
- Package catalog and per-package ACL stored in PostgreSQL (Alembic)
- Per-caller `Packages` and `Release` index rendering with a database cache
- APT client endpoints: `dists/`, `pool/`, `pubkey.gpg`, Basic or Bearer auth

## Routes and scopes

HTTP routes served by the application and what each one requires. `public` routes need no bearer token or session. A scope is checked on the access token issued by the `auth` application; the wildcards `*` and `<resource>:*` also match.

| Method | Path | Required scope / role / auth | Description |
| --- | --- | --- | --- |
| GET | `/docs` | public | Serve Swagger UI with custom static assets (only when `DOCS_ENABLED` is set) |
| GET | `/docs/oauth2-redirect` | public | OAuth2 redirect page for Swagger UI (only when `DOCS_ENABLED` is set) |
| GET | `/health` | public | Health check endpoint |
| GET | `/me` | bearer token (any scope) | Return current user profile from OIDC UserInfo |
| GET | `/pubkey.gpg` | public | Export the GPG public key used to sign `Release` |
| GET | `/dists/{suite}/Release` | public components, else credentials (token or session) | Serve the `Release` file of a suite |
| GET | `/dists/{suite}/InRelease` | public components, else credentials (token or session) | Serve the signed `InRelease` file of a suite |
| GET | `/dists/{suite}/Release.gpg` | public components, else credentials (token or session) | Serve the detached `Release.gpg` signature of a suite |
| GET | `/dists/{suite}/{component}/binary-{architecture}/Packages` | public components, else credentials (token or session) | Serve the `Packages` index of a component and architecture |
| GET | `/dists/{suite}/{component}/binary-{architecture}/Packages.gz` | public components, else credentials (token or session) | Serve the compressed `Packages.gz` index of a component and architecture |
| GET | `/pool/{component}/{prefix}/{name}/{filename}` | public package, else credentials (token or session) with read access to the package | Serve a `.deb` via `X-Accel-Redirect` after the ACL check |

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
