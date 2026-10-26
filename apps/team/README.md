# team

Multi-agent orchestration platform: AI agents, workflows, tasks and memory behind a REST API.
It is a member of the `website` uv workspace.

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
