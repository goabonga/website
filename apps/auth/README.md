# auth

Centralized OIDC/OAuth2 authentication service.

## Features

- Application foundation: Package, settings, logging, health check and Swagger UI.

## Routes and scopes

HTTP routes served by the application and what each one requires. `public` routes need no credentials.

### Service and OpenID Connect endpoints

| Method | Path | Required scope / role / auth | Description |
| --- | --- | --- | --- |
| GET | `/docs` | public | Serve Swagger UI with local static assets (no external CDN dependency) |
| GET | `/docs/oauth2-redirect` | public | OAuth2 redirect page for Swagger UI |
| GET | `/health` | public | Return a liveness signal for load balancers and container probes |

Static files are served publicly under `/static` (favicon and Swagger UI assets).

## Development

From the repository root:

```bash
uv sync --package auth
uv run --package auth uvicorn auth.main:app --reload --port 8000

uv run --package auth --group dev pytest apps/auth
uv run --package auth --group dev behave apps/auth/features
```

Settings come from environment variables (a `.env` file is loaded when present). The pytest and behave suites mock the database, Redis and SMTP, so they need no infrastructure.

Documentation: `docs/apps/auth/`.
