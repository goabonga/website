# Internal API and connection tracking

The OpenVPN server does not issue or check certificates itself. It calls
the portal through a small internal API, so that revoked or expired
certificates are refused, the routes pushed to a client follow the portal's
RBAC decision, and every session is recorded. The calls are made by the
OpenVPN `client-connect` and `client-disconnect` hooks.

## What it does

- **Validation**: given a certificate common name, answers whether it may
  connect and which routes to push. A certificate is refused when it is
  unknown (`Certificate not found`), revoked (`Certificate revoked`) or
  expired (`Certificate expired`). Refusals are logged with the client IP.
- **Connection record** (`record_connection`): stores a `vpn_connections`
  row linked to the certificate, with the connection time, the real client
  IP and the VPN address assigned by OpenVPN.
- **Disconnection record** (`record_disconnection`): finds the most recent
  open connection of the certificate, sets `disconnected_at` and the
  traffic counters reported by OpenVPN.
- **Model**: `VPNConnection`, with `is_active` (not yet disconnected) and
  `duration_seconds`. Deleting a certificate deletes its connections.

These endpoints answer `200` even for unknown certificates or connections
and report the outcome in `status`, so that a hook can decide what to do
without treating it as a transport failure.

## Endpoints

All three require the `vpn:server` scope, which is held by the machine
client used by the OpenVPN hooks (`client_credentials` grant); users
holding `vpn:connect` only are refused with `403`.

| Endpoint | Method | Request | Response |
| --- | --- | --- | --- |
| `/api/v1/internal/validate` | POST | `common_name`, `client_ip`, optional `assigned_ip` | `valid`, `reason`, `routes` |
| `/api/v1/internal/connect` | POST | `common_name`, `client_ip`, `assigned_ip` | `status`: `connected` or `certificate_not_found` |
| `/api/v1/internal/disconnect` | POST | `common_name`, `bytes_received`, `bytes_sent` (both default to `0`) | `status`: `disconnected` or `connection_not_found` |

Example validation answer:

```json
{"valid": true, "reason": null, "routes": ["10.0.0.0/8", "10.8.0.0/24"]}
```

## Data model

Table `vpn_connections` (migration `002`, applied after `001`):

| Column | Type | Notes |
| --- | --- | --- |
| `id` | UUID | Primary key |
| `certificate_id` | UUID | Foreign key to `vpn_certificates.id`, `ON DELETE CASCADE`, indexed |
| `connected_at` | timestamptz | Set by the portal when the connection is recorded |
| `disconnected_at` | timestamptz, null | Set when the disconnection is recorded |
| `assigned_ip`, `client_ip` | varchar(45) | IPv4 or IPv6 |
| `bytes_received`, `bytes_sent` | bigint | Default `0`, set on disconnection |
| `created_at`, `updated_at` | timestamptz | Maintained by the database |

Apply it with `alembic -c apps/vpn-portal/alembic.ini upgrade head`.

## Settings

None beyond those of the previous features.

## Tests

- pytest: `tests/test_connection_model.py` (columns, foreign key,
  `is_active`, `duration_seconds`, relationship),
  `tests/test_migrations.py` (revision `002`, SQL of the connections table,
  ordering, downgrade),
  `tests/test_certificate_service_connections.py` (lookup by common name,
  recording and closing connections on the in-memory session) and
  `tests/test_internal_endpoints.py` (the three routes, every refusal
  reason, validation errors, scope checks for each route).
- behave: `features/internal.feature` with scenarios for valid, unknown,
  revoked and expired certificates, recording a connection (known and
  unknown certificate), recording a disconnection (with and without an
  active connection), the wildcard scope and the unauthenticated or
  insufficient-scope calls. The database is the in-memory session.
