# knowledge

Vector storage and semantic search SaaS for AI agents, LLMs and RAG
applications. It is a member of the `website` uv workspace.

## Features

- FastAPI application with a public API and a mounted internal
  sub-application, environment-driven settings, structured logging and a
  `/health` endpoint.
- PostgreSQL data model (SQLAlchemy 2.0 with pgvector) and Alembic
  migrations.
- OAuth2 bearer authentication with JWKS validation, token exchange and
  scope checks.

The documentation of every feature lives in `docs/apps/knowledge/`.

## Routes and scopes

HTTP routes served by the application and what each one requires. `public` routes need no bearer token or session.

| Method | Path | Required scope / role / auth | Description |
| --- | --- | --- | --- |
| GET | `/health` | public | Health check endpoint |

Swagger UI (`/docs`), ReDoc (`/redoc`) and `/openapi.json` are served only when `DOCS_ENABLED` is true.

## Local development

Run every command from the root of the workspace.

```bash
uv sync --package knowledge
uv run --package knowledge uvicorn knowledge.main:app --reload --port 8003
```

Start PostgreSQL (pgvector) and apply the migrations:

```bash
docker compose -f apps/knowledge/compose.yml up -d
uv run --package knowledge alembic -c apps/knowledge/alembic.ini upgrade head
```

Settings are read from environment variables or a `.env` file in the working
directory.

## Tests

The suites use mocks and need no running database or Redis:

```bash
uv run --package knowledge --group dev pytest apps/knowledge
uv run --package knowledge --group dev behave apps/knowledge/features
```
