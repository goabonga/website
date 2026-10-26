# Mailler

Internal email sending service.

## Routes and scopes

HTTP routes served by the application and what each one requires. `public` routes need no bearer token or session.

| Method | Path | Required scope / role / auth | Description |
| --- | --- | --- | --- |
| GET | `/health` | public | Health check endpoint for monitoring |

Swagger UI (`/docs`), ReDoc (`/redoc`) and `/openapi.json` are served only when `DOCS_ENABLED` is true.

Emails, templates, contacts, groups and campaigns belong to the client of the access token (`client_id`): a caller sees and acts only on its own client, and only a holder of the `ADMIN_SCOPE` setting scope can name another one.
