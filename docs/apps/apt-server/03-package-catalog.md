# Package catalog and ACL

Every package known to the repository is a row in PostgreSQL. This feature
adds the data model, the Alembic migration and the third access control
layer: the per-package rules that decide who may read or modify a package.

## Data model

Defined in `apt_server.db.models`, created by migration `001`
(`alembic/versions/001_initial_schema.py`).

`packages`:

| Column | Description |
| --- | --- |
| `id` | UUID primary key |
| `name`, `version`, `architecture`, `suite`, `component` | Debian identity; the five together are unique (`uq_packages_identity`) |
| `owner_id` | OIDC `sub` of the uploader |
| `visibility` | `public`, `private` (default) or `shared` |
| `filename` | Pool-relative path, unique |
| `size`, `md5`, `sha1`, `sha256` | File size and checksums |
| `description`, `control` | Description and the full control stanza (JSONB) |
| `uploaded_at` | Upload timestamp (UTC) |

`package_acl`: grants a role on one package to exactly one grantee, enforced
by the check constraint `ck_package_acl_grantee_exclusive`.

| Column | Description |
| --- | --- |
| `package_id` | Foreign key to `packages`, deleted with the package |
| `grantee_user_id` | OIDC `sub` or email of the user, or null |
| `grantee_group` | Group or role claim such as `team:ops`, or null |
| `role` | `read` or `write` |
| `granted_by`, `granted_at` | Who granted the access, and when |

A grant is unique per package, grantee and role (partial unique indexes
`uq_package_acl_user` and `uq_package_acl_group`).

`index_cache` stores rendered `Packages` indexes (key, body, SHA-256,
generation time). It is created by the same migration and used by the APT
repository feature.

## The third access layer

`apt_server.acl.packages` implements the package level rules on top of the
component and scope layers. A `Caller` carries the OIDC `sub`, the scopes, the
groups, a display name (the email), and for web sessions a name, an avatar and
an `is_session` flag. `Caller.is_admin` is true with the `apt:admin` scope.

| Function | Rule |
| --- | --- |
| `visible_package_filter(caller)` | SQLAlchemy expression scoping a query: anonymous sees `public`; an authenticated caller also sees what they own and what a grant gives them (by `sub`, by email, or by group); admins see everything |
| `can_read(caller, package)` | Same rule applied to one loaded package (with its `acl` relationship) |
| `can_write(caller, package)` | Owner, admin, or an explicit `write` grant. Anonymous never writes |

Grants are matched on the caller `sub` and also on the email, because
grantees are usually entered as email addresses while the `sub` is an opaque
identifier.

## Settings

| Variable | Default | Description |
| --- | --- | --- |
| `DATABASE_URL` | `postgresql://localhost:5432/apt_server` | PostgreSQL URL; `postgres://` and `postgresql://` are rewritten to `postgresql+asyncpg://` |
| `DATABASE_ECHO` | `false` | Log every SQL statement |

`apt_server.database` builds the async engine and the `get_db` FastAPI
dependency (one session per request). The engine is disposed on shutdown.

## Migrations

```bash
export DATABASE_URL=postgresql://localhost:5432/apt_server
uv run --package apt-server alembic -c apps/apt-server/alembic.ini upgrade head
```

`DATABASE_URL` overrides the URL in `alembic.ini`. The revision chain is
kept as in the original project so existing databases stay compatible.

## Tests

The test database is SQLite (through `aiosqlite`, a development dependency of
the workspace) created with the real metadata; the JSONB type is rendered as
JSON for SQLite. No PostgreSQL server is needed.

- pytest: `tests/test_models.py` (defaults, uniqueness, cascade, grantee
  constraint, JSON control, index cache), `tests/test_package_acl.py`
  (read and write matrix, email and group grants, the visibility filter
  against a seeded catalog), `tests/test_database.py` (URL rewriting, session
  dependency) and `tests/test_migrations.py` (offline upgrade and downgrade
  SQL, single linear history).
- behave: `features/package_catalog.feature` with the scenarios "Anonymous
  callers only see public packages", "Owners also see their own private
  packages", "A user grant exposes a shared package", "A grant to an email
  address matches the display name of the caller", "A group grant exposes a
  shared package to its members", "Administrators see every package" and
  "Only owners and writers may modify a package". Scenarios tagged
  `@database` get a temporary SQLite database.
