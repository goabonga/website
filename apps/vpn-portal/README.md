# vpn-portal

Zero-Trust VPN authentication and certificate issuance service.

## Development

From the repository root:

```bash
uv sync --package vpn-portal
uv run --package vpn-portal uvicorn vpn_portal.main:app --port 8000
```

Settings come from environment variables (a `.env` file is loaded when
present).
