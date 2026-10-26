# internal

Internal admin dashboard for managing platform services.

## Routes and scopes

HTTP routes served by the application and what each one requires. `public` routes need no bearer token or session.

| Method | Path | Required scope / role / auth | Description |
| --- | --- | --- | --- |
| GET | `/health` | public | Health check endpoint (hidden from Swagger) |
| GET | `/auth/login` | public | Redirect to OAuth2 authorization endpoint |
| GET | `/auth/callback` | public | OAuth2 callback - exchange authorization code for tokens |
| GET | `/auth/logout` | public | Logout - clear authentication cookies |
| GET | `/auth/refresh` | refresh token cookie | Refresh access token using refresh token |

Swagger UI (`/docs`), ReDoc (`/redoc`) and `/openapi.json` are served only when `DOCS_ENABLED` is true.
