# Teams

A team groups the agents, workflows, tasks, conversations and memory of one
organisation. Every other object of the platform belongs to a team. This
feature adds the first database table, the migration tooling and the team
management endpoints.

## Endpoints

All routes are under `/platform/team` and need a bearer token (see
[OAuth2 authentication](02-authentication.md)).

| Method | Path | Scope | Description |
|--------|------|-------|-------------|
| POST | `/platform/team` | `team:platform:write` | Create a team (`201`) |
| GET | `/platform/team` | `team:platform:read` | List teams, newest first (`limit` 1-1000, default 100, and `offset`) |
| GET | `/platform/team/{team_id}` | `team:platform:read` | Read a team; `404 Team not found` |
| PATCH | `/platform/team/{team_id}` | `team:platform:write` | Update `name`, `description`, `config` or `is_active`; only the fields sent are changed |
| DELETE | `/platform/team/{team_id}` | `team:platform:write` | Delete a team (`204`); the pages of the following features say what happens to the objects of the team |

A team has a `name`, a unique `slug`, a `description`, a free-form `config`
object, an `is_active` flag and its creation and update timestamps. The slug
cannot be changed after creation.

## Data model and migration

Table `teams` (model `team.models.Team`, schemas `TeamCreate`, `TeamUpdate`,
`TeamResponse`): `id` (UUID), `name` (120, indexed), `slug` (255, unique),
`description` (500), `config` (JSONB), `is_active`, `created_at`, `updated_at`.

The schema is managed with Alembic, run with a synchronous connection (the
`asyncpg` part of `DATABASE_URL` is removed, `psycopg2` is used):

```bash
uv run --package team alembic -c apps/team/alembic.ini upgrade head
```

Each feature that adds tables brings its own revision: this one is
`0001_create_teams`. `alembic/env.py` imports every model so that the metadata
is complete. The standalone repository this application comes from used the
revision ids `001` to `008`; the history was re-split by feature, so a database
that was already migrated with the old ids has the right schema but an
unknown revision and must be stamped once with `alembic stamp head`.

`compose.yml` starts a PostgreSQL with the `pgvector` extension for local
development:

```bash
docker compose -f apps/team/compose.yml up -d
```

## Settings

No new setting. The routes use `DATABASE_URL` (see
[Foundation](01-foundation.md)).

## Tests

pytest: `tests/test_routes_teams.py` covers every endpoint (creation,
listing with pagination, reading, partial update, deletion, validation errors,
`404`, missing scope and missing authentication) against a mocked session;
`tests/test_models.py`, `tests/test_schemas.py` and `tests/test_main.py` gain
the team cases. `tests/test_migrations.py` renders the revisions to SQL
offline (no database) and checks that the history is linear, that every model
has its `CREATE TABLE` and that the downgrade drops every table.

behave (`features/teams.feature`) runs the real routes against an in-memory
SQLite database created from the models:

- Creating a team
- Reading a team
- Listing teams
- Listing teams page by page
- Updating a team
- Deleting a team
- Reading an unknown team
- Creating a team needs the write scope
- Listing teams needs authentication

`features/environment.py` now builds, for each scenario, the SQLite database
(PostgreSQL column types are swapped for SQLite ones in the test process only),
overrides `get_db`, and replaces the authentication clients with fakes that
answer with the scopes the scenario declares ("Given I am authenticated with
the scopes ..."). `features/steps/common_steps.py` holds the request and
response steps shared by all the following features. The SQLite driver
(`aiosqlite`) is a development dependency of the workspace.
