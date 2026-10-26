# Authorized client administration

Only OAuth2 clients that an administrator has registered may create domains.
This feature adds the `/api/v1/admin/clients` endpoints that manage the
`authorized_clients` table: which clients exist, whether they are active, how
many domains they may hold and the defaults applied to the domains they create.

Every endpoint requires **both** the administration scope (`ADMIN_SCOPE`,
`custom-domain:admin` by default) and its `:clients` variant, for example
`custom-domain:admin:clients`.

## Endpoints

The `{id}` in the paths is the numeric database id of the client, not its
OAuth2 `client_id`.

| Endpoint | Method | Description |
| --- | --- | --- |
| `/api/v1/admin/clients` | GET | List all clients ordered by name, with the number of domains each one owns (`domains_count`, soft-deleted rows included). Returns `{items, total}`. |
| `/api/v1/admin/clients` | POST | Register a client. Answers `201`. |
| `/api/v1/admin/clients/{id}` | GET | Get one client. |
| `/api/v1/admin/clients/{id}` | PUT | Partial update: only the fields present in the body change. |
| `/api/v1/admin/clients/{id}` | DELETE | Delete a client. Answers `204`. |
| `/api/v1/admin/clients/{id}/activate` | POST | Set `is_active` to true. |
| `/api/v1/admin/clients/{id}/deactivate` | POST | Set `is_active` to false. |

### Client fields

| Field | Required on creation | Description |
| --- | --- | --- |
| `client_id` | yes | OAuth2 client identifier, unique. Not editable afterwards. |
| `name` | yes | Display name. |
| `default_upstream_target` | yes | Upstream (socket path or `host:port`) used when a domain does not give one. |
| `default_cname_target` | yes | CNAME target used when a domain does not give one. |
| `description` | no | Free text. |
| `default_nginx_template_id` | no | Template used for the client's domains that have none of their own; the SSL provisioning task honours it (domain template, then this one, then the global default). |
| `max_domains` | no | Quota of live domains; omitted or null means unlimited. |
| `metadata` | no | Free-form JSON object. |
| `webhook_url`, `webhook_secret` | no | Callback for status changes (client status webhooks page). The URL needs the secret; the secret is never returned (`has_webhook_secret` tells whether one is set). |

Responses also carry `id`, `is_active`, `has_webhook_secret`, `created_at` and `updated_at`.

### Errors

- `404 Client not found`.
- `409 Client ID already exists` on creation.
- `400 Cannot delete client with N associated domains`: a client that still
  owns any domain row (soft-deleted ones included) cannot be deleted; deactivate
  it instead.

A deactivated client stays in the table but is not recognised when it asks to
register a domain (see the domain API page).

## Data model

Reads and writes the `authorized_clients` table and counts rows of
`custom_domains`; no migration is added.

## How it is tested

- pytest: `test_routes_admin_clients.py` (HTTP-level tests of each endpoint
  with a mocked session), `test_routes_admin_clients_unit.py` (route
  functions called directly, including partial updates and the metadata
  mapping) and the `TestClientSchemas` class of `test_schemas.py`.
- behave: `features/admin_clients.feature` against an in-memory database and a
  fake auth server: *Registering a client*, *A client identifier can only be
  registered once*, *Listing clients reports their domain counts*, *Updating a
  client changes only the given fields*, *Deactivating and reactivating a
  client*, *Deleting a client without domains*, *A client that owns domains
  cannot be deleted*, *An unknown client is reported* and *The clients scope
  alone is not enough*.
