# backend

Main API service of the platform, a FastAPI application. It serves a chat
endpoint with retrieval-augmented generation (RAG) over a pgvector
knowledge base, streams answers with Server-Sent Events, validates OAuth2
bearer tokens issued by the `auth` application and keeps conversations of
anonymous visitors in cookie-backed sessions. It is a member of the
`website` uv workspace.

## Routes and scopes

HTTP routes served by the application and what each one requires. `public` routes need no bearer token or session.

| Method | Path | Required scope / role / auth | Description |
| --- | --- | --- | --- |
| GET | `/health` | public | Health check endpoint for monitoring and load balancer probes |
| GET | `/.well-known/security.txt` | public | Return security.txt content (RFC 9116) |
| POST | `/api/v1/chat` | public (optional bearer token, anonymous cookie otherwise); rate limited | Chat with Server-Sent Events streaming, or conversation history with `?history=true` |

Swagger UI (`/docs`), ReDoc (`/redoc`) and `/openapi.json` are served only when `DOCS_ENABLED` is true.

## Development

Run every command from the repository root.

```bash
# Start local PostgreSQL (pgvector) and Redis
docker compose -f apps/backend/compose.yml up -d

# Apply the database migrations
uv run --package backend alembic -c apps/backend/alembic.ini upgrade head

# Run the API
uv run --package backend uvicorn backend.main:app --reload

# Run the Celery worker and the scheduler
uv run --package backend celery -A backend.celery:celery_app worker -Q backend
uv run --package backend celery -A backend.celery:celery_app beat

# Unit tests and behave scenarios (no external service needed)
uv run --package backend --group dev pytest apps/backend
uv run --package backend --group dev behave apps/backend/features
```

The full documentation, one page per feature, lives in
`docs/apps/backend/`.
