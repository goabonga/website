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
- Collections REST API (`/api/v1/collections`) with personal and
  organization ownership.
- Documents REST API with OpenAI embeddings stored in pgvector.

The documentation of every feature lives in `docs/apps/knowledge/`.

## Routes and scopes

HTTP routes served by the application and what each one requires. `public` routes need no bearer token or session. A scope is checked on the access token issued by the `auth` application; the wildcards `*` and `<resource>:*` also match.

| Method | Path | Required scope / role / auth | Description |
| --- | --- | --- | --- |
| GET | `/health` | public | Health check endpoint |
| POST | `/api/v1/collections` | bearer token; scope `collections:write` | Create a new collection |
| GET | `/api/v1/collections` | bearer token; scope `collections:read` | List all collections accessible to the authenticated user |
| GET | `/api/v1/collections/{collection_id}` | bearer token; scope `collections:read` | Get a collection by ID or slug |
| PATCH | `/api/v1/collections/{collection_id}` | bearer token; scope `collections:write` | Update a collection |
| DELETE | `/api/v1/collections/{collection_id}` | bearer token; scope `collections:write` | Delete a collection and all its documents |
| POST | `/api/v1/collections/{collection_id}/documents` | bearer token; scope `documents:write` | Add documents to a collection |
| POST | `/api/v1/collections/{collection_id}/documents/single` | bearer token; scope `documents:write` | Add a single document to a collection |
| GET | `/api/v1/collections/{collection_id}/documents` | bearer token; scope `documents:read` | List documents in a collection |
| GET | `/api/v1/documents/{document_id}` | bearer token; scope `documents:read` | Get a document by ID |
| DELETE | `/api/v1/collections/{collection_id}/documents/{document_id}` | bearer token; scope `documents:write` | Delete a document |

Swagger UI (`/docs`), ReDoc (`/redoc`) and `/openapi.json` are served only when `DOCS_ENABLED` is true.

The API routes also apply the per-collection access rules of the handlers (owner, collaborator permission, organization membership) on top of the scope.

### Scopes

The application defines no scope, it only checks the ones carried by the access tokens issued by the `auth` application, which grants them through its catalog of scopes and roles.

- `collections:write` - checked by 3 routes
- `collections:read` - checked by 2 routes
- `documents:write` - checked by 3 routes
- `documents:read` - checked by 2 routes

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
