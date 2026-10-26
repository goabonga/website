# team

Multi-agent orchestration platform: AI agents, workflows, tasks and memory behind a REST API.
It is a member of the `website` uv workspace.

## Routes and scopes

HTTP routes served by the application and what each one requires. `public` routes need no bearer token or session. A scope is checked on the access token issued by the `auth` application; the wildcards `*` and `<resource>:*` also match.

| Method | Path | Required scope / role / auth | Description |
| --- | --- | --- | --- |
| GET | `/health` | public | Health check endpoint |
| POST | `/platform/team` | scope `team:platform:write` | Create a new team |
| GET | `/platform/team` | scope `team:platform:read` | List all teams |
| GET | `/platform/team/{team_id}` | scope `team:platform:read` | Get team by ID |
| PATCH | `/platform/team/{team_id}` | scope `team:platform:write` | Update team configuration |
| DELETE | `/platform/team/{team_id}` | scope `team:platform:write` | Delete a team |

Swagger UI (`/docs`), ReDoc (`/redoc`) and `/openapi.json` are served only when `DOCS_ENABLED` is true.

### Scopes

The application defines no scope, it only checks the ones carried by the access tokens issued by the `auth` application, which grants them through its catalog of scopes and roles.

- `team:platform:write` - checked by 3 routes
- `team:platform:read` - checked by 2 routes

## Development

Run every command from the repository root.

```bash
# Install the workspace member and the dev tools
uv sync --package team --group dev

# Run the API
uv run --package team uvicorn team.main:app --reload --port 8000

# Start a local PostgreSQL (pgvector)
docker compose -f apps/team/compose.yml up -d

# Apply the database migrations
uv run --package team alembic -c apps/team/alembic.ini upgrade head

# Tests
uv run --package team --group dev pytest apps/team
uv run --package team --group dev behave apps/team/features
```

The documentation of the application is in `docs/apps/team/`: one page per
feature, with the settings, the endpoints and the tests of each.
