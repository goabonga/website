# internal

Internal admin dashboard for managing platform services.

## Routes and scopes

HTTP routes served by the application and what each one requires. `public` routes need no bearer token or session. `session` routes need a signed-in user and redirect to the login page otherwise. A scope is checked on the access token issued by the `auth` application; the wildcards `*` and `<resource>:*` also match.

| Method | Path | Required scope / role / auth | Description |
| --- | --- | --- | --- |
| GET | `/health` | public | Health check endpoint (hidden from Swagger) |
| GET | `/auth/login` | public | Redirect to OAuth2 authorization endpoint |
| GET | `/auth/callback` | public | OAuth2 callback - exchange authorization code for tokens |
| GET | `/auth/logout` | public | Logout - clear authentication cookies |
| GET | `/auth/refresh` | refresh token cookie | Refresh access token using refresh token |
| GET | `/` | session; scope `conversations:read` | Admin dashboard with chat statistics |
| GET | `/conversations` | session; scope `conversations:read` | List all conversations with pagination and search |
| GET | `/conversations/{conversation_id}` | session; scope `conversations:read` | View conversation detail with all messages |
| POST | `/conversations/{conversation_id}/delete` | session; scope `conversations:delete` | Delete a conversation and all its messages |
| POST | `/conversations/bulk-delete` | session; scope `conversations:delete` | Delete multiple conversations and all their messages |
| GET | `/analytics` | session; scope `analytics:read` | Analytics overview dashboard |
| GET | `/analytics/campaigns` | session; scope `analytics:read` | List all marketing campaigns |
| GET | `/analytics/campaigns/{campaign_id}` | session; scope `analytics:read` | View detailed campaign statistics |
| POST | `/analytics/campaigns/{campaign_id}/delete` | session; scope `analytics:write` | Delete an analytics campaign |
| POST | `/analytics/campaigns/bulk-delete` | session; scope `analytics:write` | Delete multiple analytics campaigns |
| GET | `/analytics/ips` | session; scope `analytics:read` | List IP addresses with their statistics |
| GET | `/analytics/ips/{ip_address:path}` | session; scope `analytics:read` | View detailed statistics for a specific IP address |
| POST | `/analytics/reset` | session; scope `analytics:delete` | Reset all analytics data |
| GET | `/vpn/sessions` | session; scope `vpn:admin` | List all VPN sessions with pagination |
| POST | `/vpn/sessions/{serial_number}/revoke` | session; scope `vpn:admin` | Revoke a VPN session by certificate serial number |

Swagger UI (`/docs`), ReDoc (`/redoc`) and `/openapi.json` are served only when `DOCS_ENABLED` is true.

### Scopes

The application defines no scope, it only checks the ones carried by the access tokens issued by the `auth` application, which grants them through its catalog of scopes and roles.

- `conversations:read` - checked by 3 routes
- `conversations:delete` - checked by 2 routes
- `analytics:read` - checked by 5 routes
- `analytics:write` - checked by 2 routes
- `analytics:delete` - checked by 1 route
- `vpn:admin` - checked by 2 routes
