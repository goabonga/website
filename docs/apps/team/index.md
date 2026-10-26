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

## Running the tests

```bash
uv run --package team --group dev pytest apps/team
uv run --package team --group dev behave apps/team/features
```

The pytest suite lives in `apps/team/tests/`. Each feature also has a behave
scenario file in `apps/team/features/`; the scenarios run in-process against
the ASGI application with an in-memory SQLite database and need no external
service (no PostgreSQL, no Redis, no LLM provider).
