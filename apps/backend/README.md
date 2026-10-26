# backend

Main API service of the platform, a FastAPI application. It is a member of
the `website` uv workspace.

## Routes and scopes

HTTP routes served by the application and what each one requires. `public` routes need no bearer token or session.

| Method | Path | Required scope / role / auth | Description |
| --- | --- | --- | --- |
| GET | `/health` | public | Health check endpoint for monitoring and load balancer probes |
| GET | `/.well-known/security.txt` | public | Return security.txt content (RFC 9116) |

Swagger UI (`/docs`), ReDoc (`/redoc`) and `/openapi.json` are served only when `DOCS_ENABLED` is true.

## Development

Run every command from the repository root.

```bash
# Run the API
uv run --package backend uvicorn backend.main:app --reload
```

The full documentation lives in `docs/apps/backend/`.
