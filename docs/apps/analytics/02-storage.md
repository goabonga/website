# Storage

Visitor sessions and their events are stored in PostgreSQL through async
SQLAlchemy 2. This feature adds the database layer, the first two models and
the first Alembic revision. Nothing writes to the tables yet: the endpoints
that fill them are described in the next pages.

## Database layer

`analytics.database` builds one async engine at import time from
`DATABASE_URL`:

- `postgres://` and `postgresql://` URLs are rewritten to the `asyncpg` driver
  by `get_async_database_url`; other URLs (for example
  `postgresql+asyncpg://`) are used as given.
- `async_session_maker` creates sessions with `expire_on_commit=False`.
- `get_db` is the FastAPI dependency that yields a session and always closes
  it, including when the request raises.

## Settings

| Variable | Default | Description |
| --- | --- | --- |
| `DATABASE_URL` | `postgresql://localhost:5432/analytics` | PostgreSQL URL |
| `DATABASE_ECHO` | `false` | Log every SQL statement |
| `DATA_RETENTION_DAYS` | `395` | Declared for GDPR retention; no purge job reads it yet |

## Data model

Both tables are prefixed `analytics_` and use UUID primary keys.

`analytics_sessions` (model `Session`) describes one visitor:

| Column | Notes |
| --- | --- |
| `id` | UUID primary key |
| `session_id` | Public identifier (cookie value), unique and indexed, up to 64 characters |
| `user_id` | Optional UUID of an authenticated user, indexed |
| `first_seen`, `last_seen` | Timezone-aware timestamps, set to the current UTC time by default |
| `ip_address`, `country`, `city` | Network information (`INET`, 2-letter country, city) |
| `user_agent`, `device_type`, `browser`, `browser_version`, `os`, `os_version` | Device information |
| `referrer`, `utm_source`, `utm_medium`, `utm_campaign`, `utm_term`, `utm_content` | Traffic source |
| `landing_page` | First URL seen |

`analytics_events` (model `Event`) is one tracked action:

| Column | Notes |
| --- | --- |
| `id` | UUID primary key |
| `session_id` | Foreign key to `analytics_sessions.id`, `ON DELETE CASCADE` |
| `event_type` | For example `page_view` or `click`, indexed |
| `event_data` | Free-form `JSONB` |
| `page_url`, `page_title` | Page context |
| `timestamp` | Indexed, with a composite index on `(event_type, timestamp)` |

Deleting a session deletes its events, both through the `ON DELETE CASCADE`
constraint and through the ORM relationship (`cascade="all, delete-orphan"`).

## Migrations

Alembic is configured in `apps/analytics/alembic.ini` and
`apps/analytics/alembic/env.py`. The environment imports the models, uses the
async engine and reads `DATABASE_URL` when it is set (the URL in
`alembic.ini` is only a fallback). Revision `001` creates the two tables and
their indexes.

```bash
docker compose -f apps/analytics/compose.yml up -d
cp apps/analytics/.env.example apps/analytics/.env
uv run --package analytics alembic -c apps/analytics/alembic.ini upgrade head
```

`apps/analytics/compose.yml` starts a local PostgreSQL 16 on port 5433
(database `analytics_test`), matching the `DATABASE_URL` in `.env.example`.

## Tests

pytest:

- `test_database.py`: URL conversion for each scheme and `get_db` closing the
  session, also on error.
- `test_models.py`: exported models, table names, representations, unique
  `session_id`, timestamp defaults, cascade and composite index.
- `test_migrations.py`: single linear revision chain starting at `001`, and the
  SQL rendered by `alembic upgrade head --sql` (tables, indexes, cascade,
  version stamp) without any database.
- `test_config.py`: database defaults and overrides.

behave (`features/storage.feature`) runs against a temporary SQLite database
through `aiosqlite`; `features/environment.py` renders the PostgreSQL-only
`JSONB` and `INET` types as `JSON` and `VARCHAR` for SQLite and creates the
schema from the model metadata:

- A stored session can be read back
- Session identifiers are unique
- Events belong to a session
- Event data is stored as JSON
- Deleting a session deletes its events
- Database URLs use the asyncpg driver (outline over three URL forms)

The migration itself is only checked as rendered SQL; it is not executed
against PostgreSQL by the test suites.
