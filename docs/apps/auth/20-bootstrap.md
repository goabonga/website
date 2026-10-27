# Platform bootstrap

`auth bootstrap` creates, from the settings and idempotently, what `auth` needs
before it can serve anything: its built-in scopes and roles, the platform
tenant, the Swagger UI OAuth2 client, and the registration of the users that
existed before the platform tenant. These rows used to be written by the
migrations, with the values of one deployment (a slug, a name, a redirect URI);
they are now settings, and the migrations only change the schema.

Run it after the migrations of every release, before
[`auth catalog sync`](19-catalog.md) (the catalog may extend the built-in
roles that the bootstrap creates).

## What it does

```bash
auth bootstrap [--dry-run] [--json]
```

`--dry-run` does the work in a transaction that is rolled back and reports what
would change; `--json` prints the report (`changed`, `created`, `updated`,
`skipped`, `dry_run`) for a configuration tool. Exit status: 0 on success, 2 for
invalid settings or a conflict, 1 for any other failure.

In this order, in one transaction:

1. **Built-in scopes and roles.** The scopes of `ADMIN_SCOPES` (category
   `admin`) and the roles of `DEFAULT_ROLES` (`super_admin`, `admin`,
   `user_manager`, `client_manager`, `jwks_admin`, `security_admin`, `readonly`,
   `operator`), created the way a [catalog](19-catalog.md) is: the missing ones
   are created, the existing ones are left as they are, nothing is removed. These
   are the scopes that the admin API and console authorize with, so they belong
   to the code of `auth`; the scopes of the other services do not.
2. **The platform tenant**, the tenant of the main domain. It is found by its
   `is_platform` flag, never by its slug or its id, so a tenant that exists is
   **adopted as it is**: its slug, name and id are not changed, and a difference
   with the settings is reported as `skipped`. Only when there is none is one
   created, from `PLATFORM_TENANT_SLUG`, `PLATFORM_TENANT_DISPLAY_NAME` and
   `PLATFORM_TENANT_ID` (generated when empty), active, open to all users
   (`trust_mode` `all`), with the default organisation roles (`owner`, `admin`,
   `member`). If the slug is used by a tenant that is not the platform tenant, the
   command stops (status 2) and asks for another slug.
3. **Its branding**, created once from `PLATFORM_TENANT_BRANDING` when the
   platform tenant has no branding yet; a branding that exists is never
   overwritten, since it is edited in the settings pages.
4. **Existing users.** The users with no registration tenant are registered on
   the platform tenant, the trusted sources of tenants with no trusted tenant
   point at it (they meant "the main domain"), and every user registered on it
   becomes a member with the `member` role. Once they are done, a second run has
   nothing left to do.
5. **The Swagger UI client**, `SWAGGER_CLIENT_ID`: a public client (no secret)
   for the authorization code grant, with PKCE required and no consent screen,
   allowed the redirect URIs of `SWAGGER_REDIRECT_URIS` and the scopes of
   `SWAGGER_SCOPES`. It is created when missing; when it exists, its redirect
   URIs and scopes are made to match the settings (they are managed by the
   settings, not by hand).

A run prints one line per change:

```text
created scope users:read
created role super_admin with 1 scope(s)
created platform tenant main-site
created branding of the platform tenant (primary_color)
updated 3 user(s) registered on the platform tenant
updated 3 user(s) made member of the platform tenant
created client swagger-ui
bootstrap: changed 7 item(s)
```

## Settings

| Variable | Default | Description |
| --- | --- | --- |
| `PLATFORM_TENANT_SLUG` | `platform` | Slug of the platform tenant, used only when it has to be created (lower case letters, digits and hyphens) |
| `PLATFORM_TENANT_DISPLAY_NAME` | `Platform` | Display name of the platform tenant, used only when it has to be created |
| `PLATFORM_TENANT_ID` | empty | UUID of the platform tenant to create; generated when empty |
| `PLATFORM_TENANT_BRANDING` | `{}` | JSON object of branding fields (the columns of `tenant_branding`: `primary_color`, `logo_url`, `favicon_url`...), applied once |
| `SWAGGER_CLIENT_ID` | `swagger-ui` | `client_id` of the Swagger UI client (also read by `/docs`, see [the foundation](01-foundation.md)) |
| `SWAGGER_SCOPES` | `openid profile email` | Space-separated scopes of the Swagger UI client (also requested by `/docs`) |
| `SWAGGER_REDIRECT_URIS` | `["/docs/oauth2-redirect"]` | JSON list of the redirect URIs of the Swagger UI client: the path of the redirect page of this service, or absolute URLs |

None of the defaults is a domain, a name or a colour of a deployment.

## Data model

Writes `scopes`, `roles`, `role_scopes`, `tenants` (the `is_platform` row),
`tenant_roles`, `tenant_branding`, `tenant_members`, `oauth2_clients`, and
updates `users.registration_tenant_id` and
`tenant_trusted_sources.trusted_tenant_id` where they are empty.

### Databases deployed before the migrations stopped seeding

The migrations used to insert the platform tenant, the `swagger-ui` client and
the scopes and roles of the other services. Those revisions are gone from the
chain, but the revision ids of the schema revisions are unchanged and the head is
still `060`: a database already at `060` is valid as it is and `alembic upgrade
head` does nothing. The rows the old revisions inserted stay in place; nothing
deletes them. After the first deployment of this version:

- `auth bootstrap` adopts the existing platform tenant (whatever its slug or
  id), finds the existing `swagger-ui` client and the existing built-in roles,
  and only completes what is missing. Its redirect URIs and scopes are made to
  match `SWAGGER_REDIRECT_URIS` and `SWAGGER_SCOPES`: set `SWAGGER_SCOPES` to
  the scopes the client had (the original data included the wildcard `*`) before
  running it, or the client loses them.
- `auth catalog sync` with the catalog of the deployment finds the existing
  scopes and roles of the other services and only updates what differs.

A database that was at an older revision than `060` must first be upgraded to
`060` with the original chain.

## Tests

- pytest: 2 new test modules and 1 existing modules extended.
  New modules: `tests/test_bootstrap_repository.py`, `tests/test_bootstrap_service.py`.
  Extended: `tests/test_cli.py`.
- behave: `features/bootstrap.feature` with the scenarios *A fresh database receives the built-in scopes and roles*, *The platform tenant is created from the settings*, *The identifier of the platform tenant can be chosen*, *Running it again changes nothing*, *A dry run reports the changes and applies none*, *An existing platform tenant is adopted and not renamed*, *A slug used by another tenant is refused*, *Invalid settings are refused before the database is touched*, *Existing users are registered on the platform tenant and made members*, *The Swagger UI client is created from the settings*, *The Swagger UI client follows the settings when they change*, *The catalog of a deployment extends the built-in roles after the bootstrap*.

The scenarios run the real command against the SQLite stand-in of the database,
so the SQL of the repository (including the correlated updates) is exercised;
they have not been run against PostgreSQL.
