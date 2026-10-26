# mta-sts

Minimal FastAPI service serving the MTA-STS policy (RFC 8461) at
`/.well-known/mta-sts.txt`, with a `/health` endpoint. Workspace member of the `website`
monorepo (distribution `mta-sts`, import package `mta_sts`).

## Routes and scopes

HTTP routes served by the application and what each one requires. `public` routes need no bearer token or session.

| Method | Path | Required scope / role / auth | Description |
| --- | --- | --- | --- |
| GET | `/health` | public | Health check endpoint |
| GET | `/.well-known/mta-sts.txt` | public | Serve MTA-STS policy (RFC 8461) |

No Swagger or OpenAPI documentation is exposed.

The policy is served as `text/plain` with `Cache-Control: max-age=<MTA_STS_MAX_AGE>`.

## Configuration

Read from the environment (a `.env` file is loaded when present).

| Variable | Description | Default |
| --- | --- | --- |
| `APP_NAME` | Application name | `mta-sts` |
| `LOG_LEVEL` | Logging level | `INFO` |
| `MTA_STS_MODE` | Policy mode: `enforce`, `testing` or `none` | `enforce` |
| `MTA_STS_MX` | Authorized MX hosts, comma-separated | `mail.goabonga.com` |
| `MTA_STS_MAX_AGE` | Policy max age in seconds | `86400` |

## Development

```bash
uv sync --package mta-sts
uv run --package mta-sts pytest apps/mta-sts
uv run --package mta-sts behave apps/mta-sts/features
```
