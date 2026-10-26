# Nginx template administration

Administrators can replace the default nginx configuration with templates
stored in the database. This feature adds the `/api/v1/admin/templates`
endpoints that create, edit, validate, activate and apply those templates.

Every endpoint requires **both** the administration scope (`ADMIN_SCOPE`,
`custom-domain:admin` by default) and its `:templates` variant, for example
`custom-domain:admin:templates` (see the OAuth2 authentication page; a
`custom-domain:*` wildcard also works).

## How a template is chosen

During provisioning (SSL provisioning page) a domain uses, in this order, its
own active template (`nginx_template_id`), then the active default template of
its client (see the client administration page), then the active template
flagged as default, then the files shipped with the package. Templates can be
shared or owned by one client (per-client template ownership page); a template
owned by another client is never used. A template holds a
`http_template` and a `https_template`, both Jinja2 sources rendered with the
context listed in the nginx rendering page.

## Endpoints

| Endpoint | Method | Description |
| --- | --- | --- |
| `/api/v1/admin/templates` | GET | List all templates ordered by name, with `domains_count` (domains whose `nginx_template_id` is the template). Returns `{items, total}`. |
| `/api/v1/admin/templates` | POST | Create a template. `slug`, `name`, `http_template` and `https_template` are required; `description` and `available_variables` are optional. Answers `201`. The new template is active and not the default. |
| `/api/v1/admin/templates/{id}` | GET | Get one template. |
| `/api/v1/admin/templates/{id}` | PUT | Partial update of `name`, `description`, `http_template`, `https_template`, `available_variables` and `is_active`. Changed sources are validated first. |
| `/api/v1/admin/templates/{id}` | DELETE | Delete a template. Answers `204`. |
| `/api/v1/admin/templates/{id}/validate` | POST | Render both templates with `test_variables` and check the nginx syntax. |
| `/api/v1/admin/templates/{id}/set-default` | POST | Make this template the default and clear the flag on every other one. |
| `/api/v1/admin/templates/{id}/reprovision` | POST | Re-run SSL provisioning for the domains using this template. |

### Errors

- `404` when the template does not exist.
- `409 Template slug already exists` on creation.
- `400 Invalid HTTP template: [...]` / `Invalid HTTPS template: [...]` when a
  source does not compile (the error list contains messages such as `Syntax
  error at line 2: ...`).
- `400 Cannot delete the default template`.
- `400 Cannot delete template with N associated domains` (every domain row
  counts, including soft-deleted ones).

### Validation

`POST .../validate` takes `{"test_variables": {...}}`. It renders the HTTP and
HTTPS templates (syntax and render errors are collected in `errors`), and when
both render it joins them and runs the nginx syntax check. The check needs the
privileged helper, which the API process never starts, so it is delegated to a
worker: `template_service.validate_nginx_syntax_in_worker` queues the Celery task
`validate_nginx_template` (`custom_domain.tasks.validation`) and waits for its
answer for at most `TEMPLATE_VALIDATION_TIMEOUT_SECONDS`. The task calls
`validate_nginx_syntax` (nginx rendering page), where the helper wraps the text
in the contexts nginx needs. When no worker answers (or the broker is down) the
error list contains *Nginx syntax error: Nginx validation unavailable: ...* and
`nginx_syntax_valid` is false; the rest of the validation is still returned. The
response is `{valid, rendered_http, rendered_https, nginx_syntax_valid, errors}`.
The certificate files named by the templates must exist for nginx to accept
them, so the check is a hint for new domains, not a guarantee.

### Reprovisioning

`POST .../reprovision` takes `{"only_active": true, "dry_run": false}` (both
optional, shown with their defaults). It selects the domains whose
`nginx_template_id` is the template (only the `active` ones when `only_active`
is true; soft-deleted domains are not excluded, but the task ignores them) and
queues `provision_domain_ssl` for each. With `dry_run` nothing is queued and the
response only reports the number of matching domains. The answer is
`{domains_affected, success, failed, errors}`; a domain whose task could not be
queued is counted in `failed` with the error. Domains that fall back to the
default template are not selected.

## Data model

Reads and writes the `nginx_templates` table; no migration is added.

## How it is tested

- pytest: `test_routes_admin_templates.py` (HTTP-level tests of every
  endpoint with a mocked session), `test_routes_admin_templates_unit.py`
  (route functions called directly, including the partial-update paths) and the
  `TestTemplateSchemas` class of `test_schemas.py`; `test_tasks_validation.py`
  and the `validate_nginx_syntax_in_worker` tests of `test_services_template.py`
  cover the worker delegation.
- behave: `features/admin_templates.feature` runs the API against an in-memory
  database with a fake auth server: creating a template, duplicate slug,
  syntax error, listing with domain counts, choosing a new default, refusing to
  delete the default or a template in use, deleting an unused template,
  validation with test variables, the delegation of the nginx check to a worker,
  dry-run and real reprovisioning, and the
  missing-scope case. The shared steps `I send a ... request to ... with JSON`
  and the `{kind:name}` path placeholders are reused by the next features.
