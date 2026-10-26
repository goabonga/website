# Admin API

Administrators need to see who is on the VPN and to cut a session off
without waiting for the certificate to expire. This feature adds both,
behind the `vpn:admin` scope.

## What it does

- **Session list**: every certificate that is neither revoked nor expired
  counts as an active session, newest first. For each one the portal adds
  the latest connection recorded by the OpenVPN hooks: the connection time
  and the assigned VPN address. A certificate that has not been seen by the
  hooks yet is reported with its issuance time and the address `N/A`.
- **Pagination**: `page` (from 1) and `per_page` (1 to 100, default 50);
  `total` is the number of active certificates, whatever the page.
- **Revocation**: revokes a certificate by serial number, with the reason
  `admin_revoked`, through the same service as the user-initiated
  disconnection: the Step-CA revocation is attempted, a Step-CA failure is
  logged, and the record is revoked in the database in any case. A revoked
  certificate is refused by `/api/v1/internal/validate` from then on, and the
  renegotiation hook of the [hook scripts](08-openvpn-hook-scripts.md) cuts the
  client off at its next TLS renegotiation.

## Endpoints

| Endpoint | Method | Scope | Description |
| --- | --- | --- | --- |
| `/api/v1/admin/sessions` | GET | `vpn:admin` | List active sessions (`?page=1&per_page=50`) |
| `/api/v1/admin/sessions/{serial}` | DELETE | `vpn:admin` | Revoke the certificate with this serial number |

A session looks like:

```json
{
  "id": "<certificate uuid>",
  "user_id": "<user uuid>",
  "username": "alice@example.com",
  "device_name": "laptop",
  "connected_at": "2026-01-01T10:00:00Z",
  "assigned_ip": "10.8.0.2",
  "certificate_serial": "3f9a...",
  "expires_at": "2026-01-01T10:10:00Z",
  "scopes": ["vpn:connect"],
  "routes": ["10.8.0.0/24"]
}
```

The list answers `{"sessions": [...], "total": 1, "page": 1, "per_page": 50}`.
The revocation answers `{"status": "revoked", "serial_number": "...",
"revoked_at": "..."}`, or `404` when the serial is unknown. Both routes
answer `401` without a valid token and `403` without `vpn:admin` (the
`vpn:*` wildcard is accepted).

## Settings

None beyond those of the previous features.

## Data model

Reads `vpn_certificates` and `vpn_connections`; nothing is added.

## Tests

- pytest: `tests/test_admin_endpoints.py` (empty list, filtering of
  revoked and expired certificates, session fields, latest connection,
  fallback values, pagination and its validation, revocation, `404`,
  Step-CA outage, access control for both routes), on the in-memory
  session.
- behave: `features/admin.feature` with the scenarios *List active
  sessions when none exist*, *List active sessions with results*, *List
  sessions with pagination*, *Sessions show the assigned VPN address*, the
  unauthenticated and insufficient-scope cases, *Revoke an active session*,
  *Revoked sessions are no longer listed* and *Revoke a nonexistent
  session*.
