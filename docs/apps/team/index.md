# team

`team` is a multi-agent orchestration platform. It manages autonomous AI agents,
their teams, conversations, workflows, tasks and shared memory behind a REST
API. It is a member of the uv workspace (`apps/team`, import package `team`).

The application is built feature by feature. Each page below documents one
feature: what it does, its endpoints and settings, its data model, and how it
is tested with pytest and behave.

| Page | Feature |
|------|---------|
| [Foundation](01-foundation.md) | settings, logging, database session, health check, CORS |
| [OAuth2 authentication](02-authentication.md) | bearer token validation, scopes and token exchange |
| [Teams](03-teams.md) | teams CRUD and the first database migration |
| [Agents](04-agents.md) | agents of a team |
| [Conversations](05-conversations.md) | conversations, participants and messages |
| [Memory](06-memory.md) | team memory entries with embeddings |
| [Skills](07-skills.md) | Agent Skills attached to agents |
| [Workflows](08-workflows.md) | multi-step workflow definitions |
| [Tasks](09-tasks.md) | tasks, agent state, execution log and cancellation |
| [Usage reporting](10-usage.md) | execution events reported by services |
| [Tool registry](11-tools.md) | tool catalog and the platform tools |
| [Service tools](12-service-tools.md) | tools calling the other platform services |
| [Workspace tools](13-workspace-tools.md) | files, git, GitHub and SQL tools |
| [LLM completions](14-llm.md) | chat completions with tool calling for OpenAI and Anthropic |
| [Agent runner](15-agent-runner.md) | Celery worker that executes a task with an agent |
| [Task dispatch](16-task-dispatch.md) | periodic dispatch, auto orchestration and webhook events |
| [Maintenance](17-maintenance.md) | log and workspace cleanup, memory summarization |
| [Seed data](18-seed-data.md) | the GOABONGA team, its agents and skills |

## Running the tests

```bash
uv run --package team --group dev pytest apps/team
uv run --package team --group dev behave apps/team/features
```

The pytest suite lives in `apps/team/tests/`. Each feature also has a behave
scenario file in `apps/team/features/`; the scenarios run in-process against
the ASGI application with an in-memory SQLite database and need no external
service (no PostgreSQL, no Redis, no LLM provider).
