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
| POST | `/platform/{team_id}/agents` | scope `team:platform:write` | Create a new AI agent |
| GET | `/platform/{team_id}/agents` | scope `team:platform:read` | List agents for a team |
| GET | `/platform/{team_id}/agents/{agent_id}` | scope `team:platform:read` | Get agent by ID |
| PATCH | `/platform/{team_id}/agents/{agent_id}` | scope `team:platform:write` | Update agent configuration |
| DELETE | `/platform/{team_id}/agents/{agent_id}` | scope `team:platform:write` | Delete an agent |
| POST | `/platform/conversations` | scope `team:platform:write` | Create a new multi-agent conversation |
| GET | `/platform/conversations` | scope `team:platform:read` | List all conversations |
| GET | `/platform/conversations/{conversation_id}` | scope `team:platform:read` | Get conversation by ID |
| POST | `/platform/conversations/{conversation_id}/agents/{agent_id}` | scope `team:platform:write` | Attach an agent to a conversation |
| DELETE | `/platform/conversations/{conversation_id}` | scope `team:platform:write` | Delete a conversation |
| POST | `/platform/conversations/{conversation_id}/messages` | scope `team:write` | Post a message inside a conversation |
| GET | `/platform/conversations/{conversation_id}/messages` | scope `team:read` | List messages for a conversation |
| POST | `/platform/{team_id}/workflows` | scope `team:platform:write` | Create a new workflow |
| GET | `/platform/{team_id}/workflows` | scope `team:platform:read` | List workflows for a team |
| PATCH | `/platform/{team_id}/workflows/{workflow_id}` | scope `team:platform:write` | Update workflow configuration |
| DELETE | `/platform/{team_id}/workflows/{workflow_id}` | scope `team:platform:write` | Delete a workflow |
| POST | `/platform/{team_id}/tasks` | scope `team:platform:write` | Create a new task |
| POST | `/platform/{team_id}/tasks/{task_id}/cancel` | scope `team:platform:write` | Cancel a task |
| GET | `/platform/{team_id}/memory` | scope `team:platform:read` | Access shared memory for a team |
| POST | `/platform/{team_id}/memory` | scope `team:platform:write` | Create a memory entry for a team |
| PATCH | `/platform/{team_id}/memory/{entry_id}` | scope `team:platform:write` | Update a memory entry's content and/or metadata |
| DELETE | `/platform/{team_id}/memory/{entry_id}` | scope `team:platform:write` | Delete a memory entry |
| POST | `/platform/{team_id}/agents/{agent_id}/skills` | scope `team:platform:write` | Create a new skill for an agent |
| GET | `/platform/{team_id}/agents/{agent_id}/skills` | scope `team:platform:read` | List skills for an agent (name + description only) |
| GET | `/platform/{team_id}/agents/{agent_id}/skills/{skill_id}` | scope `team:platform:read` | Get a skill by ID (includes full content) |
| PATCH | `/platform/{team_id}/agents/{agent_id}/skills/{skill_id}` | scope `team:platform:write` | Update a skill |
| DELETE | `/platform/{team_id}/agents/{agent_id}/skills/{skill_id}` | scope `team:platform:write` | Delete a skill |
| GET | `/platform/{team_id}/conversations` | scope `team:platform:read` | List conversations for a team |
| GET | `/platform/{team_id}/conversations/count` | scope `team:platform:read` | Get conversation count for a team |
| POST | `/usage/{team_id}/report` | scope `team:write` | Report a task execution event |
| POST | `/usage/{team_id}/batch` | scope `team:write` | Batch report agent activity |

Swagger UI (`/docs`), ReDoc (`/redoc`) and `/openapi.json` are served only when `DOCS_ENABLED` is true.

### Scopes

The application defines no scope, it only checks the ones carried by the access tokens issued by the `auth` application, which grants them through its catalog of scopes and roles.

- `team:platform:write` - checked by 20 routes
- `team:platform:read` - checked by 12 routes
- `team:write` - checked by 3 routes
- `team:read` - checked by 1 route

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
