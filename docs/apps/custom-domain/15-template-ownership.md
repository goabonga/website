# Per-client nginx template ownership

Several applications (clients) share one custom-domain service. Their domains are
rendered from nginx templates, and a template written for one application must
not end up on another's domains. This feature gives a template an optional owner:
a **shared** template belongs to nobody and can be used by every client, a
**client-owned** template can only be used by its owner.

## Who may do what

| Action | Who |
| --- | --- |
| Create, edit, delete, validate, reprovision a template | Administrators only (`ADMIN_SCOPE` and its `:templates` variant) |
| Create a template for a client | An administrator, with `client_id` in the body |
| List the templates one can choose | Any registered client (`custom-domain:read`) |
| Put a template on a domain | The domain's client, with `custom-domain:write` |

Clients cannot create templates. A template becomes nginx configuration that root
loads, so letting an application write its own would let it define server blocks
for names that are not its own. An administrator reviews the source and assigns it
to the client.

## Data model

`nginx_templates.client_id` (nullable string, indexed) holds the OAuth2
`client_id` of the owner; `NULL` means shared. It is added by the alembic
revision `002_template_owner` (`alembic upgrade head`); existing templates stay
shared. The slug remains unique across all templates, so a client-owned slug must
not collide with a shared one (an easy convention is to prefix it with the client).

## Rules

A client may use a template when it is active and either shared or owned by that
client. The rule is applied at every place a template is chosen:

- `POST /domains` and `PUT /domains/{id}` with `nginx_template_id` answer `400
  Nginx template not found or not available to this client` otherwise. When an
  administrator updates a domain the rule is checked against the **domain's**
  client, not the administrator.
- `POST` and `PUT /admin/clients` with `default_nginx_template_id` apply the rule
  to the client being created or edited (the id used to be accepted without any
  check).
- The SSL provisioning task applies it again when it resolves the template of a
  domain (the domain's own template, then the client's default, then the global
  default), so a row written around the API, or a template reassigned later, still
  cannot leak: another client's template is skipped.
- The **global default** must be shared: `POST /admin/templates/{id}/set-default`
  answers `400 A client-owned template can not be the global default`, and the
  provisioning task only considers shared templates as the global default.

## Endpoints

| Endpoint | Method | Description |
| --- | --- | --- |
| `/api/v1/admin/templates` | POST | Accepts `client_id` (optional). The response and the list items carry `client_id`. |
| `/api/v1/admin/templates?client_id=<id>` | GET | Only the templates owned by that client. |
| `/api/v1/admin/templates?shared=true` / `shared=false` | GET | Only shared templates / only client-owned templates. |
| `/api/v1/templates` | GET | `custom-domain:read`. The active templates the caller may use: `{items: [{id, slug, name, description, shared}], total}`. The sources are not returned. Administrators see every active template. |

`client_id` can not be changed after creation: create a new template and move the
domains instead.

## Settings

None.

## How it is tested

- pytest: `test_template_ownership.py` covers the model and the migration SQL, the
  rule in `get_usable_template`, the domain create and update routes, the admin
  template routes (owner stored, list filters, default refused), the client default
  check, the client-facing list (including over HTTP and the registry check) and the
  queries of the provisioning task; the existing admin template tests were
  adapted to the new field.
- behave: `features/template_ownership.feature` creates a client-owned template as
  an administrator, lists by owner, shows a client its own templates only, registers
  and updates domains with usable and foreign templates, refuses the default and
  client-default cases, and provisions a domain with the client's default template
  and with a foreign one (ignored).
