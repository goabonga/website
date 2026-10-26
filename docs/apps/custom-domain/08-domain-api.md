# Domain API

This is the feature customers' applications use: register a custom domain,
follow its status, change its upstream, restart verification or provisioning
and delete it. It wires the DNS verification and SSL provisioning tasks of the
previous features behind HTTP endpoints, and adds `domain_service`.

## Domain lifecycle

```
pending -> dns_verifying -> dns_verified -> ssl_provisioning -> active
                 |                                   |            |
                 +---------------> failed <----------+            |
                                                                  v
                       any status -> deprovisioning -> (deleted)
```

Registration creates the domain as `pending` and queues DNS verification; the
Celery tasks do the rest. `suspended` and `expired` exist in the status enum
but nothing sets them yet. `deprovisioning` is entered by `DELETE` and left by
the worker, which soft-deletes the domain (below).

## Endpoints

All paths are under `/api/v1/domains`. A caller only sees and edits the
domains of its own client (the `client_id` claim of the token); a caller whose
resolved scopes include the administration scope (`ADMIN_SCOPE`,
`custom-domain:admin` by default) sees every client's domains. Accessing another
client's domain answers `403 Access denied`, an unknown or soft-deleted one `404
Domain not found`.

**The client registry is checked on every request**, not only when a domain is
created: the caller's `client_id` must belong to an authorized client that is
active, otherwise the answer is `403 Client not authorized` (`403 Client ID
required` when the token carries no client). Deactivating a client therefore
takes effect on its next call, on every endpoint of this page and of the events
page. Holders of the administration scope are operators, not registered clients,
and skip this check.

| Endpoint | Method | Scope | Description |
| --- | --- | --- | --- |
| `/api/v1/domains` | GET | `custom-domain:read` | List domains. Query: `status_filter`, `owner_id`, `include_deleted` (default false), `limit` (20), `offset` (0). Returns `{items, total, limit, offset}`, newest first. |
| `/api/v1/domains` | POST | `custom-domain:write` | Register a domain. |
| `/api/v1/domains/lookup/{name}` | GET | `custom-domain:lookup` | Return the owner data of an **active** domain (meant for middleware routing requests by host name). Only the caller's own domains are found: another client's domain answers `404`, like an unknown one. The administration scope may look up any client's domain. |
| `/api/v1/domains/{id}` | GET | `custom-domain:read` | Domain details. |
| `/api/v1/domains/{id}` | PUT | `custom-domain:write` | Change `upstream_target`, `nginx_template_id` or `metadata` (only the fields sent and not null). |
| `/api/v1/domains/{id}` | DELETE | `custom-domain:write` | Start the deletion. Answers `202 {id, status: "deprovisioning", message}`. |
| `/api/v1/domains/{id}/verify` | POST | `custom-domain:write` | Restart DNS verification. |
| `/api/v1/domains/{id}/provision` | POST | `custom-domain:write` | Restart SSL provisioning. |

### Registering a domain

Body: `domain` (required), `owner_id` (required, the tenant that owns the
domain), `owner_type` (default `organization`), and the optional
`upstream_target`, `cname_target`, `nginx_template_id` and `metadata`. The
upstream (a socket path or `host:port`, validated, see the TCP upstream targets page) defaults to the caller's client `default_upstream_target`; the CNAME to
its `default_cname_target`, then to the `DEFAULT_CNAME_TARGET` setting. Nothing
is built in: when no value can be found the answer is `400 No upstream target`
or `400 No CNAME target`.

Checks, in order: the name is valid (at most 255 characters, DNS label
syntax) or `400`; no live domain has the same name (case-insensitive, the name is
stored in lower case) or `409 Domain already registered`; the token carries a
`client_id` or `403 Client ID required`; the client is registered and active or
`403 Client not authorized`; the client's `max_domains` quota counting non-deleted
domains is not reached or `403 Domain limit reached (N)`.

The answer (`201`) holds the new `id`, `status` (`pending`), `cname_target` and
a `dns_instructions` sentence telling the customer which CNAME record to create.
DNS verification is queued at once.

### Updating and deleting

`PUT` only stores the new values; the nginx files are rendered again by the next
provisioning run (call `/provision`, or reprovision the template). It answers
`409 Domain is being deleted` for a domain in `deprovisioning`.

`DELETE` is asynchronous because removing the nginx file and revoking the
certificate need privileges that the API process does not have. The request sets
the status `deprovisioning` (and the error message `Deleted by user`), queues the
`deprovision_domain` task and answers `202`. The worker removes the nginx
configuration, reloads nginx, revokes the certificate and finally sets
`deleted_at` (SSL provisioning page). Until then the domain is still returned,
with the status `deprovisioning`, and its name can not be registered again; once
it is done the domain answers `404` and the name is free. A failed deprovisioning
leaves the domain in `failed` with the error: send `DELETE` again to retry.
Repeating `DELETE` while the work is pending queues it again, which is harmless.
The row is kept for `SOFT_DELETE_PURGE_DAYS` days.

### Restarting the pipeline

`/verify` is accepted in the statuses `pending`, `failed` and `dns_verifying`;
it resets `retry_count`, sets `dns_verifying` and queues the verification task.
`/provision` is accepted in `dns_verified`, `failed` and `active`; it sets
`ssl_provisioning` and queues the provisioning task. Any other status answers
`400 Cannot verify/provision domain in status <status>`. Both answer
`{id, status, message}`.

## Domain service

`custom_domain.services.domain_service` groups domain logic used by the routes
and by tests:

- `get_authorized_client(db, client_id)` returns the active client row.
- `validate_domain_name(name)` returns `(is_valid, error)`.
- `verify_dns(db, domain)` runs the DNS check inside the caller's database
  session. The API does not use it; the tasks do the work.

Nothing in the service starts a privileged command: the API process never runs
anything with `sudo`. Template resolution lives with the tasks that use it.

The checks of the client registry are in `custom_domain.routes.access`
(`require_client_scopes`, `ensure_client_authorized`).

## Settings

| Variable | Default | Description |
| --- | --- | --- |
| `DEFAULT_CNAME_TARGET` | empty | CNAME used when neither the request nor the client gives one. |

## How it is tested

- pytest: `test_routes_domains.py` (HTTP-level tests of each endpoint),
  `test_routes_domains_unit.py` (route functions and the ownership helper called
  directly, including the quota, include-deleted and null-field paths),
  `test_routes_domains_scoping.py` (lookup ownership, target resolution,
  updates during deletion), `test_routes_access.py` (the registry check on every
  endpoint), `test_services_domain.py` (results, name validation, DNS
  verification) and the `TestDomainSchemas` class of `test_schemas.py`.
- behave: `features/domain_api.feature` covers registering a domain, invalid
  names, duplicates, unknown clients, the quota, per-client listing and the
  admin view, cross-client access, lookup of active and inactive domains and of another
  client's domain, a deactivated client refused everywhere, the CNAME fallback
  and its absence, update, the asynchronous deletion up to the re-registration
  of the name, restarting verification and provisioning, the refused
  transitions and the missing write scope. The database is in-memory, the auth
  server is faked and the Celery queues are recorded instead of used.
