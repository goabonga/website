# vpn-portal

Zero-Trust VPN authentication and certificate issuance service, a FastAPI
application. Users authenticate with an OAuth2 / OIDC access token; the
portal checks their `vpn:*` scopes, has the internal Step-CA sign a
short-lived client certificate (10 to 15 minutes) and returns it with a
ready-to-use OpenVPN profile. The OpenVPN server reports back through the
helper scripts of this application, which keeps an audit trail of
certificates and connections in PostgreSQL. It is a member of the `website`
uv workspace.

## Routes and scopes

HTTP routes served by the application and what each one requires. `public` routes need no bearer token or session. A scope is checked on the access token issued by the `auth` application; the wildcards `*` and `<resource>:*` also match.

| Method | Path | Required scope / role / auth | Description |
| --- | --- | --- | --- |
| GET | `/health` | public | Health check endpoint |
| POST | `/api/v1/vpn/connect` | scope `vpn:connect` | Generate VPN bundle (certificate, key, config) |
| POST | `/api/v1/vpn/disconnect` | scope `vpn:connect` | Disconnect and revoke current certificate |
| GET | `/api/v1/vpn/status` | scope `vpn:connect` | Get current VPN connection status |
| GET | `/api/v1/vpn/ca` | scope `vpn:connect` | Get the root CA certificate from the Step-CA server |
| POST | `/api/v1/internal/validate` | scope `vpn:server` | Validate certificate for OpenVPN client-connect script |
| POST | `/api/v1/internal/connect` | scope `vpn:server` | Record VPN connection for OpenVPN client-connect script |
| POST | `/api/v1/internal/disconnect` | scope `vpn:server` | Record VPN disconnection for OpenVPN client-disconnect script |
| GET | `/api/v1/admin/sessions` | scope `vpn:admin` | List active VPN sessions |
| DELETE | `/api/v1/admin/sessions/{serial_number}` | scope `vpn:admin` | Revoke a VPN session by certificate serial number |

Swagger UI (`/docs`), ReDoc (`/redoc`) and `/openapi.json` are served only when `DOCS_ENABLED` is true.

### Scopes

The application defines no scope, it only checks the ones carried by the access tokens issued by the `auth` application, which grants them through its catalog of scopes and roles.

- `vpn:connect` - checked by 4 routes
- `vpn:server` - scope of the machine client that calls the internal API from the OpenVPN hooks; checked by 3 routes
- `vpn:admin` - checked by 2 routes

## Hook scripts

`scripts/openvpn.py` runs on the OpenVPN server as `client-connect`,
`client-disconnect` and `tls-verify` hook (`--connect`, `--disconnect`,
`--reneg`). It authenticates with the OAuth2 `client_credentials` grant and
calls the internal API. It needs only `httpx`
(`requirements-openvpn.txt`).

## Development

From the repository root:

```bash
uv sync --package vpn-portal
uv run --package vpn-portal uvicorn vpn_portal.main:app --port 8000
uv run --package vpn-portal --group dev pytest apps/vpn-portal
uv run --package vpn-portal --group dev behave apps/vpn-portal/features
uv run --package vpn-portal alembic -c apps/vpn-portal/alembic.ini upgrade head
```

Settings come from environment variables (a `.env` file is loaded when
present). The optional `compose.yml` starts a local PostgreSQL (port 5443)
and Redis (port 6390) for manual runs; the tests need neither.

Documentation: `docs/apps/vpn-portal/`.
