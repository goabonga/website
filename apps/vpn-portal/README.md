# vpn-portal

Zero-Trust VPN authentication and certificate issuance service.

## Routes and scopes

HTTP routes served by the application and what each one requires. `public` routes need no bearer token or session.

| Method | Path | Required scope / role / auth | Description |
| --- | --- | --- | --- |
| GET | `/health` | public | Health check endpoint |

Swagger UI (`/docs`), ReDoc (`/redoc`) and `/openapi.json` are served only when `DOCS_ENABLED` is true.

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
