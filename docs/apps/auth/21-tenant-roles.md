# Synchronisation of the system roles of the organisations

Every organisation has three system roles, `owner`, `admin` and `member`, created
from `DEFAULT_TENANT_ROLES` (see the [data model](02-data-model.md)) when the
organisation is created. They are stored, and never updated afterwards: a scope
added to the defaults in a later release (the `admin` role now holds
`domain:read`) reaches the new organisations only. `auth tenant-roles sync`
brings the system roles of the existing organisations up to the defaults,
idempotently, and is safe to run after the migrations of every release.

## What it does

```bash
auth tenant-roles sync [--dry-run] [--json]
```

- `--dry-run` does all the work in a transaction that is rolled back: the report
  shows what would change and nothing is written.
- `--json` prints the report as a JSON document (`changed`, `created`, `updated`,
  `skipped`, `dry_run`, plus `tenants`); `changed` is what a configuration tool
  reads to tell whether the run changed anything.
- Exit status: 0 on success, 1 for any failure (an unreachable database, for
  example); the arguments are checked by the parser (status 2).

For every organisation, in the order of their slugs, and for each of `owner`,
`admin` and `member`:

- A system role that is **missing** is created as a new organisation gets it
  (display name, description, scopes, order). The `member` role is the default
  role of the organisation only if the organisation has no default role.
- The default scopes that the role does not **grant yet** are appended to its
  scopes. A scope counts as granted when the role holds it exactly, through the
  wildcard of its resource (`domain:*` grants `domain:read`) or through `*`, so an
  organisation that gave its admins `domain:*` gets nothing added and the owner
  (`*`) never changes.
- A role with a system name that is **not a system role** (a custom role called
  `admin`) is reported as `skipped` and left alone.
- **Nothing is removed or reworded.** The scopes an organisation added to a
  system role, its display names and descriptions, the custom roles and the
  members are untouched. The one thing the command cannot know is why a default
  scope is absent: a scope that an organisation deliberately removed from a
  system role comes back with the next run. Use `--dry-run` to see the changes
  first.

A run prints one line per change, then a total:

```text
updated organisation acme role admin (+domain:read)
created organisation beta role member with 1 scope(s)
tenant roles: changed 2 item(s)
```

The JSON report lists, under `tenants`, the organisations that changed, with the
roles created and the scopes added to each role:

```json
{
  "changed": true,
  "created": ["organisation beta role member with 1 scope(s)"],
  "updated": ["organisation acme role admin (+domain:read)"],
  "skipped": [],
  "tenants": {
    "acme": {"created": [], "added": {"admin": ["domain:read"]}},
    "beta": {"created": ["member"], "added": {}}
  },
  "dry_run": false
}
```

### Not part of the bootstrap

[`auth bootstrap`](20-bootstrap.md) does not run it. The bootstrap only completes
what a deployment needs to serve; changing the roles of organisations that
customers manage is a decision of the operator, taken after reading a dry run.
The deployment of the Ansible collection runs it after `auth catalog sync`, with
`--dry-run` in check mode (see [the auth catalog](../../ansible/09-auth-catalog.md)).

## Settings

This feature adds no setting.

## Data model

Writes `tenant_roles` (`scopes` of the system roles, and the rows of the missing
ones). Reads `tenants`.

## Tests

- pytest: 1 new test module and 2 existing modules extended.
  New module: `tests/test_tenant_role_sync.py`.
  Extended: `tests/test_cli.py`, `tests/test_tenant_role_repository.py`.
- behave: `features/tenant_roles.feature` with the scenarios *The admin role of an existing organisation receives the new scope*, *Running it again changes nothing*, *A dry run reports the changes and applies none*, *The JSON report says what each organisation received*, *What an organisation customised is kept, and so are its custom roles*, *A missing system role is created* and *The bootstrap does not change the system roles of the organisations*.

The scenarios run the real command against the SQLite stand-in of the database;
they have not been run against PostgreSQL.
