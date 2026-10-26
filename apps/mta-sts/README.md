# mta-sts

Minimal FastAPI service, workspace member of the `website` monorepo
(distribution `mta-sts`, import package `mta_sts`).

## Routes and scopes

HTTP routes served by the application and what each one requires. `public` routes need no bearer token or session.

| Method | Path | Required scope / role / auth | Description |
| --- | --- | --- | --- |
| GET | `/health` | public | Health check endpoint |

No Swagger or OpenAPI documentation is exposed.

## Configuration

Read from the environment (a `.env` file is loaded when present).

| Variable | Description | Default |
| --- | --- | --- |
| `APP_NAME` | Application name | `mta-sts` |
| `LOG_LEVEL` | Logging level | `INFO` |

## Development

```bash
uv sync --package mta-sts
uv run --package mta-sts pytest apps/mta-sts
uv run --package mta-sts behave apps/mta-sts/features
```
