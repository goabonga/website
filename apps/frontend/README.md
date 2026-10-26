# frontend

Frontend application server (FastAPI) for the website, with its Vite and
TypeScript web client in `web/`. The server currently exposes a health
endpoint, a configurable CORS policy and logging split between stdout and
stderr. The web client build generates the Jinja2 template stored in
`src/frontend/templates/index.html`.

## Routes and scopes

HTTP routes served by the application and what each one requires. `public` routes need no bearer token or session.

| Method | Path | Required scope / role / auth | Description |
| --- | --- | --- | --- |
| GET | `/health` | public | Health check endpoint for monitoring |

Swagger UI (`/docs`), ReDoc (`/redoc`) and `/openapi.json` are served only when `DOCS_ENABLED` is true.
