# frontend

Frontend application server (FastAPI) for the website, with its Vite and
TypeScript web client in `web/`. The server renders the generated template
`src/frontend/templates/index.html` for every page, injecting its runtime
configuration from environment variables, and serves the client build under
`/static`. It also exposes `/.well-known/security.txt` (RFC 9116), reports
page views to an analytics service, and provides a health endpoint, a
configurable CORS policy and logging split between stdout and stderr.

## Routes and scopes

HTTP routes served by the application and what each one requires. `public` routes need no bearer token or session.

| Method | Path | Required scope / role / auth | Description |
| --- | --- | --- | --- |
| GET | `/health` | public | Health check endpoint for monitoring |
| GET | `/{path:path}` | public | Serve the single page application for all unmatched routes |
| GET | `/.well-known/security.txt` | public | Return security.txt content (RFC 9116) |

Swagger UI (`/docs`), ReDoc (`/redoc`) and `/openapi.json` are served only when `DOCS_ENABLED` is true.

The built web client and other static files are served publicly under `/static`.
