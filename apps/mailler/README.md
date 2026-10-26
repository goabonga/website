# Mailler

Internal email sending service.

## Routes and scopes

HTTP routes served by the application and what each one requires. `public` routes need no bearer token or session. A scope is checked on the access token issued by the `auth` application; the wildcards `*` and `<resource>:*` also match.

| Method | Path | Required scope / role / auth | Description |
| --- | --- | --- | --- |
| GET | `/health` | public | Health check endpoint for monitoring |
| POST | `/api/v1/send` | scope `mailler:send` | Send an email immediately (async via Celery) |
| POST | `/api/v1/schedule` | scope `mailler:send` | Schedule an email for future delivery |
| GET | `/api/v1/emails` | scope `mailler:read` | List the emails of the calling client with pagination |
| GET | `/api/v1/emails/{email_id}` | scope `mailler:read` | Get email details by ID |
| GET | `/api/v1/stats` | scope `mailler:stats` | Get the email sending statistics of the calling client (real-time from emails table) |
| GET | `/api/v1/providers` | scope `mailler:read` | List available (configured) email providers |

Swagger UI (`/docs`), ReDoc (`/redoc`) and `/openapi.json` are served only when `DOCS_ENABLED` is true.

Emails, templates, contacts, groups and campaigns belong to the client of the access token (`client_id`): a caller sees and acts only on its own client, and only a holder of the `ADMIN_SCOPE` setting scope can name another one.

### Scopes

The application defines no scope, it only checks the ones carried by the access tokens issued by the `auth` application, which grants them through its catalog of scopes and roles.

- `mailler:send` - checked by 2 routes
- `mailler:read` - checked by 3 routes
- `mailler:stats` - checked by 1 route
