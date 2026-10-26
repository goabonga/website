# Certificate records and migrations

Every certificate issued by the portal is recorded in PostgreSQL. The
records are the audit trail (who got a certificate, when, with which
scopes and routes), the basis of revocation and the source of truth that
the OpenVPN hooks query on each connection. This feature adds the database
layer and the first table; the code that writes to it arrives with the
certificate issuance feature.

## What it does

- `vpn_portal.db.base`: the SQLAlchemy declarative `Base`, with a naming
  convention for indexes and constraints so that Alembic generates stable
  names, and a `TimestampMixin` adding `created_at` and `updated_at`
  (timezone-aware, set by the database, `updated_at` refreshed on update).
- `vpn_portal.db.session`: an asyncpg engine, an `async_sessionmaker`
  (sessions do not expire on commit) and the `get_db` FastAPI dependency
  that yields a session and closes it afterwards. `postgresql://` and
  `postgres://` URLs are rewritten to `postgresql+asyncpg://`; the engine
  is created when the module is imported but only connects on first use.
- `vpn_portal.db.models.VPNCertificate`: the `vpn_certificates` table, with
  the computed properties `is_revoked`, `is_expired` and `is_valid`
  (neither revoked nor expired).
- Alembic: `alembic.ini` and `alembic/`, with an async `env.py` that takes
  the database URL from the portal settings.

## Data model

Table `vpn_certificates`:

| Column | Type | Notes |
| --- | --- | --- |
| `id` | UUID | Primary key |
| `user_id` | UUID | Subject of the OIDC token; indexed |
| `username` | varchar(255) | Name or e-mail of the user |
| `serial_number` | varchar(64) | Certificate serial in hexadecimal; unique and indexed |
| `common_name` | varchar(255) | `vpn-<user_id>-<timestamp>`; indexed |
| `not_before`, `not_after` | timestamptz | Validity window; `not_after` is indexed |
| `device_name` | varchar(255), null | Optional device label sent by the client |
| `scopes` | varchar(64)[] | Scopes held by the user at issuance |
| `assigned_routes` | varchar(64)[] | CIDR routes pushed to the client |
| `revoked_at` | timestamptz, null | Set on revocation; indexed |
| `revocation_reason` | varchar(255), null | For example `user_requested` or `admin_revoked` |
| `created_at`, `updated_at` | timestamptz | Maintained by the database |

The private key of a certificate is never stored.

## Migration

Revision `001` creates the table and its five indexes. Alembic commands
are run from the repository root:

```bash
uv run --package vpn-portal alembic -c apps/vpn-portal/alembic.ini upgrade head
uv run --package vpn-portal alembic -c apps/vpn-portal/alembic.ini current
uv run --package vpn-portal alembic -c apps/vpn-portal/alembic.ini upgrade head --sql
```

`alembic.ini` sets `script_location` relative to itself, so the commands
work from any directory. `alembic/env.py` imports the models and uses
`DATABASE_URL` (read through the settings, the URL of `alembic.ini` is only
a placeholder). With `--sql` the migration is rendered for PostgreSQL
without connecting to a database.

## Settings

| Variable | Default | Description |
| --- | --- | --- |
| `DATABASE_URL` | `postgresql://localhost:5432/vpn_portal` | PostgreSQL URL |
| `DATABASE_POOL_SIZE` | `5` | Connections kept in the pool |
| `DATABASE_MAX_OVERFLOW` | `10` | Extra connections allowed beyond the pool |
| `DATABASE_ECHO` | `false` | Log every SQL statement |

## Tests

- pytest: `tests/test_db_base.py` (naming convention, timestamp mixin),
  `tests/test_db_session.py` (URL rewriting, pool settings, `get_db`
  lifecycle), `tests/test_certificate_model.py` (columns, indexes,
  `is_revoked` / `is_expired` / `is_valid`) and `tests/test_migrations.py`
  (single head, SQL rendered for PostgreSQL covers every model column,
  downgrade).
- behave: `features/database.feature` with the scenarios *Database URLs are
  converted to the asyncpg driver*, *Heroku-style database URLs are
  converted too*, *A fresh certificate is valid*, *A revoked certificate is
  not valid*, *An expired certificate is not valid*, *The migration creates
  the certificates table* and *The migrations have a single head*.
- Neither suite connects to PostgreSQL: the migrations are checked as
  generated SQL.
