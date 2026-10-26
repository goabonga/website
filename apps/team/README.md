# team

Multi-agent orchestration platform: AI agents, workflows, tasks and memory behind a REST API.
It is a member of the `website` uv workspace.

## Routes and scopes

HTTP routes served by the application and what each one requires. `public` routes need no bearer token or session.

| Method | Path | Required scope / role / auth | Description |
| --- | --- | --- | --- |
| GET | `/health` | public | Health check endpoint |

Swagger UI (`/docs`), ReDoc (`/redoc`) and `/openapi.json` are served only when `DOCS_ENABLED` is true.

## Development

Run every command from the repository root.

```bash
# Install the workspace member and the dev tools
uv sync --package team --group dev

# Run the API
uv run --package team uvicorn team.main:app --reload --port 8000

# Tests
uv run --package team --group dev pytest apps/team
uv run --package team --group dev behave apps/team/features
```

The documentation of the application is in `docs/apps/team/`: one page per
feature, with the settings, the endpoints and the tests of each.
