# custom-domain

Centralized service for managing custom domains with DNS verification and SSL provisioning.

## Routes and scopes

HTTP routes served by the application and what each one requires. `public` routes need no bearer token or session. A scope is checked on the access token issued by the `auth` application; the wildcards `*` and `<resource>:*` also match.

| Method | Path | Required scope / role / auth | Description |
| --- | --- | --- | --- |
| GET | `/` | public | Root endpoint |
| GET | `/health` | public | Health check endpoint |
| GET | `/api/v1/domains` | scope `custom-domain:read`; client registered and active | List domains for the authenticated client |
| POST | `/api/v1/domains` | scope `custom-domain:write`; client registered and active | Register a new custom domain |
| GET | `/api/v1/domains/lookup/{domain_name}` | scope `custom-domain:lookup`; client registered and active | Lookup an active domain by name (for middleware) |
| GET | `/api/v1/domains/{domain_id}` | scope `custom-domain:read`; client registered and active | Get domain details |
| PUT | `/api/v1/domains/{domain_id}` | scope `custom-domain:write`; client registered and active | Update a domain |
| DELETE | `/api/v1/domains/{domain_id}` | scope `custom-domain:write`; client registered and active | Delete a domain |
| POST | `/api/v1/domains/{domain_id}/verify` | scope `custom-domain:write`; client registered and active | Trigger DNS verification for a domain |
| POST | `/api/v1/domains/{domain_id}/provision` | scope `custom-domain:write`; client registered and active | Trigger SSL provisioning for a domain |
| GET | `/api/v1/domains/{domain_id}/status` | scope `custom-domain:read`; client registered and active | Get current domain status for polling |
| GET | `/api/v1/domains/{domain_id}/events` | scope `custom-domain:read`; client registered and active | Stream domain provisioning events via SSE |
| GET | `/api/v1/domains/{domain_id}/events/history` | scope `custom-domain:read`; client registered and active | Get event history for a domain |
| GET | `/api/v1/admin/clients` | scopes `custom-domain:admin`, `custom-domain:admin:clients` (all) (`ADMIN_SCOPE` setting) | List all authorized clients |
| POST | `/api/v1/admin/clients` | scopes `custom-domain:admin`, `custom-domain:admin:clients` (all) (`ADMIN_SCOPE` setting) | Create a new authorized client |
| GET | `/api/v1/admin/clients/{client_id}` | scopes `custom-domain:admin`, `custom-domain:admin:clients` (all) (`ADMIN_SCOPE` setting) | Get client details |
| PUT | `/api/v1/admin/clients/{client_id}` | scopes `custom-domain:admin`, `custom-domain:admin:clients` (all) (`ADMIN_SCOPE` setting) | Update a client |
| DELETE | `/api/v1/admin/clients/{client_id}` | scopes `custom-domain:admin`, `custom-domain:admin:clients` (all) (`ADMIN_SCOPE` setting) | Delete a client |
| POST | `/api/v1/admin/clients/{client_id}/deactivate` | scopes `custom-domain:admin`, `custom-domain:admin:clients` (all) (`ADMIN_SCOPE` setting) | Deactivate a client |
| POST | `/api/v1/admin/clients/{client_id}/activate` | scopes `custom-domain:admin`, `custom-domain:admin:clients` (all) (`ADMIN_SCOPE` setting) | Activate a client |
| GET | `/api/v1/admin/stats/overview` | scopes `custom-domain:admin`, `custom-domain:admin:stats` (all) (`ADMIN_SCOPE` setting) | Get overview statistics |
| GET | `/api/v1/admin/stats/top-clients` | scopes `custom-domain:admin`, `custom-domain:admin:stats` (all) (`ADMIN_SCOPE` setting) | Get top clients by domain count |
| GET | `/api/v1/admin/stats/recent-activity` | scopes `custom-domain:admin`, `custom-domain:admin:stats` (all) (`ADMIN_SCOPE` setting) | Get recent domain activity |
| GET | `/api/v1/admin/stats/dashboard` | scopes `custom-domain:admin`, `custom-domain:admin:stats` (all) (`ADMIN_SCOPE` setting) | Get complete dashboard data |
| GET | `/api/v1/admin/templates` | scopes `custom-domain:admin`, `custom-domain:admin:templates` (all) (`ADMIN_SCOPE` setting) | List all nginx templates |
| POST | `/api/v1/admin/templates` | scopes `custom-domain:admin`, `custom-domain:admin:templates` (all) (`ADMIN_SCOPE` setting) | Create a new nginx template |
| GET | `/api/v1/admin/templates/{template_id}` | scopes `custom-domain:admin`, `custom-domain:admin:templates` (all) (`ADMIN_SCOPE` setting) | Get template details |
| PUT | `/api/v1/admin/templates/{template_id}` | scopes `custom-domain:admin`, `custom-domain:admin:templates` (all) (`ADMIN_SCOPE` setting) | Update a template |
| DELETE | `/api/v1/admin/templates/{template_id}` | scopes `custom-domain:admin`, `custom-domain:admin:templates` (all) (`ADMIN_SCOPE` setting) | Delete a template |
| POST | `/api/v1/admin/templates/{template_id}/validate` | scopes `custom-domain:admin`, `custom-domain:admin:templates` (all) (`ADMIN_SCOPE` setting) | Validate a template with test variables |
| POST | `/api/v1/admin/templates/{template_id}/set-default` | scopes `custom-domain:admin`, `custom-domain:admin:templates` (all) (`ADMIN_SCOPE` setting) | Set a template as the default |
| POST | `/api/v1/admin/templates/{template_id}/reprovision` | scopes `custom-domain:admin`, `custom-domain:admin:templates` (all) (`ADMIN_SCOPE` setting) | Reprovision all domains using this template |

Swagger UI (`/docs`), ReDoc (`/redoc`) and `/openapi.json` are served only when `DOCS_ENABLED` is true.

Client-scoped routes also require the caller's client to be registered and active; holders of the `ADMIN_SCOPE` setting scope (default `custom-domain:admin`) are exempt.

### Scopes

The application defines no scope, it only checks the ones carried by the access tokens issued by the `auth` application, which grants them through its catalog of scopes and roles.

- `custom-domain:read` - checked by 5 routes
- `custom-domain:write` - checked by 5 routes
- `custom-domain:lookup` - checked by 1 route
- `custom-domain:admin` - checked by 19 routes
- `custom-domain:admin:clients` - required together with `custom-domain:admin` by the administration routes (derived from the `ADMIN_SCOPE` setting); checked by 7 routes
- `custom-domain:admin:stats` - required together with `custom-domain:admin` by the administration routes (derived from the `ADMIN_SCOPE` setting); checked by 4 routes
- `custom-domain:admin:templates` - required together with `custom-domain:admin` by the administration routes (derived from the `ADMIN_SCOPE` setting); checked by 8 routes
