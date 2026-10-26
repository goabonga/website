# MJML email templates

Reusable email templates written in [MJML](https://mjml.io/), compiled to
HTML when they are saved and rendered with Jinja2 variables on demand.

Templates are private to the client that created them (see
[client identity](02-authentication.md)): a client lists, reads, edits,
deletes and renders only its own templates, and slugs are unique per client,
so two applications can both have a `welcome` template. A template of another
client is reported as `404`. Administrators can act on every client.

## Endpoints

All routes live under `/api/v1/templates`.

| Endpoint | Method | Scope | Description |
| --- | --- | --- | --- |
| `/templates` | GET | `mailler:read` | Paginated list of the client's templates (`page`, `page_size`, `status`, `search` on name and slug; `client_id` for administrators) |
| `/templates` | POST | `mailler:write` | Create a template (`201`); administrators may set `client_id` in the body to create it for another client |
| `/templates/{id}` | GET | `mailler:read` | Read by numeric id |
| `/templates/by-slug/{slug}` | GET | `mailler:read` | Read by slug inside the caller's client (`client_id` query parameter for administrators) |
| `/templates/{id}` | PUT | `mailler:write` | Update (partial body) |
| `/templates/{id}` | DELETE | `mailler:write` | Delete (`204`) |
| `/templates/compile` | POST | `mailler:read` | Compile MJML to HTML without saving |
| `/templates/{id}/render` | POST | `mailler:read` | Render subject, HTML and plain text with the given variables |

## Behaviour

- A template has an owner (`client_id`), a `slug` unique for that client
  (lowercase letters and digits separated by single hyphens or underscores,
  up to 100 characters, for example `welcome` or `workspace_invitation`), a `name`, a `subject_template`, an
  `mjml_source`, an optional `description`, `plain_text` and `metadata`.
- MJML is compiled with `mrml` when the template is created or its source
  changes; compilation errors give `400` and nothing is saved. The result is
  kept in `html_compiled`.
- `variables` is the list of Jinja2 variables used by the subject and the
  MJML source (`{{ name }}`); it is extracted automatically unless supplied.
- New templates are `draft`. The status can be changed through `PUT` to
  `draft`, `active` or `archived`.
- A duplicate slug inside the same client gives `409`, an unknown id or slug,
  or a template of another client, `404`. Naming another client without
  being an administrator gives `403`.
- Rendering (`mailler.services.rendering`, shared with campaigns) uses a
  Jinja2 sandbox, because templates are written by the clients: a template
  cannot reach Python internals or the host (`400`, "Template not allowed").
  The HTML body is auto-escaped, so a value such as `<b>` cannot inject
  markup; the subject and the plain text version are not HTML and keep the
  values as they are. Plain text may use `%name%` instead of `{{ name }}`.
  A template that has not been
  compiled or a template syntax error gives `400`, as does an undefined
  variable error (a plain missing variable renders as an empty string; only
  operations on it, such as attribute access, raise). The response
  contains the rendered `subject`, `html` and, when a plain text version
  exists, `plain_text`.
- `mailler.services.mjml` also provides `html_to_plain_text` and
  `validate_mjml` helpers.

## Data model and migration

Alembic revision `002` creates `email_templates` (`client_id` required and
indexed, unique `(client_id, slug)`, status indexed, `variables` as a
PostgreSQL array, `metadata` as JSONB, `created_at` and `updated_at`).

## Dependencies

`mrml` (MJML compiler, Rust bindings), `beautifulsoup4` (plain text
extraction) and `jinja2` (sandboxed rendering).

## How it is tested

- pytest: `tests/test_routes_templates.py`, `tests/test_services_mjml.py`,
  `tests/test_services_rendering.py`,
  `tests/test_models_template.py`, plus the scope checks through the real
  template routes in `tests/test_auth_integration.py`.
- behave: `features/templates.feature` (listing with search and status
  filters, creation, duplicate and invalid slug, invalid MJML, reads by id
  and slug, update, status change, delete, compile, render, scopes and
  authentication, escaping, the sandbox, underscores in slugs, and the
  isolation between clients: same slug in two
  clients, foreign templates hidden and read-only, administrator access). The MJML compiler runs for real; the database is the
  in-process SQLite one, where PostgreSQL arrays are stored as JSON.
