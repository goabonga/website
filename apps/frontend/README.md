# frontend

Frontend application server (FastAPI) for the website, with its Vite and
TypeScript web client in `web/`. The server renders the generated template
`src/frontend/templates/index.html` for every page, injecting its runtime
configuration from environment variables, and serves the client build under
`/static`. It also exposes a health endpoint, a configurable CORS policy and
logging split between stdout and stderr.

## Routes and scopes

HTTP routes served by the application and what each one requires. `public` routes need no bearer token or session.

| Method | Path | Required scope / role / auth | Description |
| --- | --- | --- | --- |
| GET | `/health` | public | Health check endpoint for monitoring |
| GET | `/{path:path}` | public | Serve the single page application for all unmatched routes |

Swagger UI (`/docs`), ReDoc (`/redoc`) and `/openapi.json` are served only when `DOCS_ENABLED` is true.

The built web client and other static files are served publicly under `/static`.
