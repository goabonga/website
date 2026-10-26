# knowledge

Vector storage and semantic search SaaS for AI agents, LLMs and RAG
applications. It is a member of the `website` uv workspace.

## Features

- FastAPI application with a public API and a mounted internal
  sub-application, environment-driven settings, structured logging and a
  `/health` endpoint.

The documentation of every feature lives in `docs/apps/knowledge/`.

## Local development

Run every command from the root of the workspace.

```bash
uv sync --package knowledge
uv run --package knowledge uvicorn knowledge.main:app --reload --port 8003
```

Settings are read from environment variables or a `.env` file in the working
directory.

## Tests

The suites use mocks and need no running database or Redis:

```bash
uv run --package knowledge --group dev pytest apps/knowledge
uv run --package knowledge --group dev behave apps/knowledge/features
```
