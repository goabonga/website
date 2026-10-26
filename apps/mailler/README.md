# Mailler

Internal email sending service.

## Routes and scopes

HTTP routes served by the application and what each one requires. `public` routes need no bearer token or session. A scope is checked on the access token issued by the `auth` application; the wildcards `*` and `<resource>:*` also match.

| Method | Path | Required scope / role / auth | Description |
| --- | --- | --- | --- |
| GET | `/health` | public | Health check endpoint for monitoring |
| GET | `/api/v1/providers` | scope `mailler:read` | List available (configured) email providers |

Swagger UI (`/docs`), ReDoc (`/redoc`) and `/openapi.json` are served only when `DOCS_ENABLED` is true.

Emails, templates, contacts, groups and campaigns belong to the client of the access token (`client_id`): a caller sees and acts only on its own client, and only a holder of the `ADMIN_SCOPE` setting scope can name another one.

### Scopes

The application defines no scope, it only checks the ones carried by the access tokens issued by the `auth` application, which grants them through its catalog of scopes and roles.

- `mailler:read` - checked by 1 route
