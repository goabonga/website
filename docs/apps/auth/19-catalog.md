# Catalog of scopes and roles

The scopes and roles of the services that rely on `auth` (which scope a
service checks, which role holds it, which machine client may use it) are data
of a deployment, not behaviour of `auth`. They are declared in a JSON catalog
file and applied to the database by `auth catalog sync`, an idempotent command
that is safe to run after the migrations of every release.

## What it does

### The command line

`auth` is a console script of the package (`auth.cli:main`, also reachable as
`python -m auth`). The first command is:

```bash
auth catalog sync [--file PATH] [--dry-run] [--json]
```

- `--file` names the catalog; without it the `CATALOG_FILE` setting is used.
  When neither is given the command exits with status 2.
- `--dry-run` does all the work in a transaction that is rolled back: the report
  shows what would change and nothing is written.
- `--json` prints the report as a JSON document (`changed`, `created`,
  `updated`, `skipped`, `dry_run`); `changed` is what a configuration tool
  reads to tell whether the run changed anything.
- Exit status: 0 on success, 2 for an unusable catalog or arguments, 1 for any
  other failure (an unreachable database, for example).

### The catalog file

```json
{
  "version": 1,
  "scopes": [
    {"name": "notes:read", "description": "Read notes"},
    {"name": "notes:write", "description": "Write notes", "category": "app"}
  ],
  "roles": [
    {
      "name": "notes_editor",
      "description": "Edit notes",
      "scopes": ["notes:read", "notes:write"]
    }
  ],
  "clients": [
    {
      "client_id": "<client id of a machine client>",
      "allowed_scopes": ["notes:read"],
      "allowed_grant_types": ["client_credentials"]
    }
  ]
}
```

Every key is optional; an unknown key is an error (a typo must not silently
disable a scope).

| Entry | Keys | Defaults |
| --- | --- | --- |
| scope | `name` (required, `resource:action` or `*`, up to 100 characters), `description`, `resource`, `action`, `category`, `is_system`, `is_active` | `resource` and `action` are the first and the last parts of the name (`billing:checkout:write` is resource `billing`, action `write`; `*` is `*`/`*`; set `action` for another value); `category` is `api`; `is_system` and `is_active` are true |
| role | `name` (required), `description`, `scopes`, `is_system` | no scope; `is_system` true |
| client | `client_id` (required), `allowed_scopes`, `allowed_grant_types` | empty lists |

### What a synchronisation does

- A scope or role that does not exist is created. A scope is created with the
  resource, action, category and flags of its entry.
- The description of an existing scope or role is updated when the entry has a
  different one (an entry without `description` leaves it alone). The other
  attributes of an existing scope are not touched: they may have been edited in
  the administration console.
- The scopes listed for an existing role are added to it.
- The scopes and grant types listed for an **existing** OAuth2 client are added to
  its allowances. A client that does not exist is reported as `skipped` and never
  created here (clients and their secrets are created by the deployment).
- **Nothing is ever deleted or removed**: a scope that disappears from the file,
  or that was added to a role by hand, stays. A scope that a role lists must
  exist, in the catalog or already in the database; otherwise the command stops
  with status 2 before it writes anything.

The built-in scopes and roles of `auth` itself (`ADMIN_SCOPES` and
`DEFAULT_ROLES`, the authorization of its admin API and console) are part of the
code, not of the catalog (the seed actions of the [administration
console](16-admin-ui.md) create them). A catalog can still name a built-in role,
to give it a scope of another service, provided the scope is declared too.

A synchronisation prints one line per change:

```text
created scope notes:read
created role notes_editor with 2 scope(s)
updated scope notes:write (description)
updated role notes_editor (+notes:share)
updated client kb-client (+notes:read, +client_credentials)
skipped client absent-client (not found)
catalog: changed 5 item(s)
```

## Settings

| Variable | Default | Description |
| --- | --- | --- |
| `CATALOG_FILE` | empty | Path of the catalog file that `auth catalog sync` reads when `--file` is not given |

## Data model

Writes `scopes`, `roles`, `role_scopes` and, for the allowances, the
`allowed_scopes` and `allowed_grant_types` columns of `oauth2_clients`. There
is no table for the catalog itself: the file is the source of truth and the
database holds its result.

## Tests

- pytest: 4 new test modules.
  New modules: `tests/test_catalog_repository.py`, `tests/test_catalog_service.py`, `tests/test_cli.py`, plus the in-memory repository `tests/fakes_catalog.py`.
- behave: `features/catalog.feature` with the scenarios *The first synchronisation creates the scopes and the roles*, *Running it again changes nothing*, *A dry run reports the changes and applies none*, *Descriptions are updated and scopes are added to existing roles, nothing is removed*, *The listed allowances are added to an existing client only*, *A role may only hold known scopes*, *A malformed catalog is refused*, *The catalog file comes from the CATALOG_FILE setting*, *Without a file the command explains what is missing*.

The behave scenarios run the real command (`auth.cli.main`) against the SQLite
stand-in of the database, so the SQL of the repository is exercised too; they
have not been run against PostgreSQL.
