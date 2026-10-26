# vpn-portal

Zero-Trust VPN authentication and certificate issuance service.

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

Swagger UI (`/docs`), ReDoc (`/redoc`) and `/openapi.json` are served only when `DOCS_ENABLED` is true.

### Scopes

The application defines no scope, it only checks the ones carried by the access tokens issued by the `auth` application, which grants them through its catalog of scopes and roles.

- `vpn:connect` - checked by 4 routes
- `vpn:server` - scope of the machine client that calls the internal API from the OpenVPN hooks; checked by 3 routes

## Development

From the repository root:

```bash
uv sync --package vpn-portal
uv run --package vpn-portal uvicorn vpn_portal.main:app --port 8000
uv run --package vpn-portal --group dev pytest apps/vpn-portal
uv run --package vpn-portal --group dev behave apps/vpn-portal/features
```

Settings come from environment variables (a `.env` file is loaded when
present).

Documentation: `docs/apps/vpn-portal/`.
