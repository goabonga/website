# Database migrations

The PostgreSQL schema is managed with Alembic. The configuration, the
environment script and the revisions live next to the package in
`apps/backend/alembic/` and `apps/backend/alembic.ini`.

## Configuration

- `alembic.ini` sets `script_location` relative to itself, so the commands
  work from any directory.
- `alembic/env.py` imports `backend.database.Base` and the models so that
  `target_metadata` is complete, and runs the migrations through the async
  engine (`asyncpg`).
- `DATABASE_URL` overrides `sqlalchemy.url`; `postgres://` and
  `postgresql://` are rewritten to `postgresql+asyncpg://`. Without it the
  placeholder URL of `alembic.ini` is used.

```bash
# From the repository root
uv run --package backend alembic -c apps/backend/alembic.ini upgrade head
uv run --package backend alembic -c apps/backend/alembic.ini current

# Print the SQL without touching a database
DATABASE_URL=postgresql://user:pass@localhost/db \
  uv run --package backend alembic -c apps/backend/alembic.ini upgrade head --sql
```

## Local infrastructure

`apps/backend/compose.yml` starts a PostgreSQL 16 with pgvector and a Redis 7
for development, on the non-default host ports 5438 and 6385, with health
checks. The database name, user and password it creates are throw-away
development values: read them in the file and build `DATABASE_URL` from them.

```bash
docker compose -f apps/backend/compose.yml up -d
```

## Revision history

The history is a single linear chain of 14 revisions, numbered `001` to
`014`; the head is `014_add_knowledge_status`.

| Revision | Change |
|----------|--------|
| `001_initial_schema` | Enables the `vector` extension; creates `conversations`, `messages`, `anonymous_sessions`, `knowledge_base`, `usage_logs` |
| `002_drop_current_conversation_id` | Removes `current_conversation_id` from `anonymous_sessions` |
| `003_add_conversation_summary` | Adds `conversations.summary` |
| `004_add_knowledge_namespaces` | Creates `knowledge_namespaces` and `knowledge_base.namespace_id` |
| `005_add_system_prompts` | Creates `system_prompts` and `system_prompt_versions` |
| `006` to `012` | Created email templates, contacts, campaigns and their analytics (a newsletter feature that later moved to the mailer service) and added `conversations.archived_at` (`008`) |
| `013_drop_email_tables_migrated_to_mailler` | Drops the email tables again |
| `014_add_knowledge_status` | Adds `status` and `validation_details` to `knowledge_base` |

Revisions `006`, `007`, `009`, `010`, `011` and `012` are kept because
databases deployed before the move already recorded them; on a fresh
database they create tables that `013` removes. The final schema matches the
models of the previous pages. Note that the prompt tables exist only through
revision `005`; `SystemPrompt` is not imported by the model package, so
autogenerate would not see it.

## Tests

- pytest: `tests/test_migrations.py` checks that the history has one head and
  one base, is numbered without gaps, and renders to SQL offline (no database)
  with every model table created, the email tables dropped and the head
  revision recorded.
- behave: `features/migrations.feature` ("The history has a single head", "A
  fresh database receives every application table", "Email tables moved to
  the mailer service are dropped", "The upgrade records the head revision").
  Both use Alembic's offline SQL mode, so no PostgreSQL is needed.
