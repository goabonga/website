# Python client SDK

`custom_domain.client` is a typed Python client for the HTTP API. Other
services of the platform use it to register customer domains and follow them
without writing HTTP calls. It only needs `httpx`.

```python
from custom_domain.client import CustomDomainClient

with CustomDomainClient("https://custom-domain.example.com", access_token="...") as client:
    created = client.domains.create(
        domain="app.example.com", owner_id="org_123", owner_type="organization"
    )
    print(created.dns_instructions)

    active = client.domains.wait_for_active(created.id, timeout=600, poll_interval=5)
    print(active.status, active.ssl_expires_at)
```

## Synchronous client

`CustomDomainClient(base_url, access_token, timeout=30, token_refresher=None)`
sends the token as a bearer header. When the service answers `401` and a
`token_refresher` callable was given, the token is refreshed and the request is
repeated once. The client is a context manager (`close()` releases the
connection), and `health()` calls `/health`.

It exposes four namespaces:

| Namespace | Methods |
| --- | --- |
| `domains` | `list(status, owner_id, include_deleted, limit, offset)`, `create(domain, owner_id, owner_type, ...)`, `get(id)`, `update(id, ...)`, `delete(id)`, `lookup(name)`, `verify(id)`, `provision(id)`, `get_status(id)`, `get_event_history(id, limit)`, `stream_events(id, timeout)`, `wait_for_active(id, timeout, poll_interval, on_status_change)` |
| `clients` | `list()`, `create(...)`, `get(id)`, `update(id, ...)`, `delete(id)`, `activate(id)`, `deactivate(id)` |
| `templates` | `list()`, `create(...)`, `get(id)`, `update(id, ...)`, `delete(id)`, `set_default(id)`, `validate(id, test_variables)`, `reprovision(id, only_active, dry_run)` |
| `stats` | `overview()`, `top_clients(limit)`, `recent_activity(limit)`, `dashboard()` |

They map one to one to the endpoints of the domain API, client
administration, template administration and statistics pages (the admin
namespaces need the matching admin scopes). Responses are parsed into
dataclasses: `Domain`, `DomainCreate`, `DomainStatus_`, `DomainLookup`,
`DomainList`, `Client`, `ClientList`, `Template`, `TemplateList`, `OverviewStats`
and `SSEEvent`; the `DomainStatus` enum mirrors every status the server can
report, `deprovisioning` included (a test compares the two).

### What a SaaS application needs

An application that sells custom domains to its tenants needs only the
`domains` namespace, with a token that carries `custom-domain:read` and
`custom-domain:write` (and `custom-domain:lookup` to resolve host names): register
(`create`), restart verification (`verify`) or provisioning (`provision`), read
the state (`get`, `get_status`, `get_event_history`, `stream_events`,
`wait_for_active`), list (`list`), update the upstream or template (`update`),
delete (`delete`), look a host name up (`lookup`, which only finds the
caller's own domains) and list the nginx templates it may choose
(`list_available_templates`, per-client template ownership page). Onboarding such an application (client registration and
scopes) is described in the SaaS onboarding page.

`delete(id)` is asynchronous, like the endpoint: it answers
`{"id", "status": "deprovisioning", "message"}` and a worker finishes the job.
Poll `get(id)` (or `get_status(id)`) until it raises `NotFoundError`.

`wait_for_active` polls `get_status` until the domain is `active` and then
returns the full `Domain`. It raises `CustomDomainError` when the domain
becomes `failed` (the message carries the server's reason) or when `timeout`
seconds pass.

`stream_events` yields `SSEEvent` objects from the server-sent events stream of
the events page. It opens its own `httpx.stream` connection with the bearer
token instead of reusing the client's connection.

### Errors

HTTP errors become exceptions that carry `status_code` and `detail`:

| Status | Exception |
| --- | --- |
| 400 | `ValidationError` |
| 401 | `AuthenticationError` |
| 403 | `AuthorizationError` |
| 404 | `NotFoundError` |
| 409 | `ConflictError` |
| other | `CustomDomainError`, the base class of all of them |

## Asynchronous client

`AsyncCustomDomainClient(base_url, access_token, timeout=30)` is an
`async with` context manager covering the domain lifecycle: `list_domains`,
`create_domain`, `get_domain`, `update_domain`, `delete_domain`, `verify_domain`,
`provision_domain`, `lookup_domain`, `list_available_templates`, `get_domain_status`
and `get_event_history`. HTTP errors raise the same typed exceptions as the
synchronous client (they share one mapping). There is no token refresh, no SSE
stream and no administration namespace.

## Differences from the source application

The client was written for the service and some calls did not match the API it
talks to. The migrated client fixes them:

- `templates.validate` posts to `/admin/templates/{id}/validate` with
  `test_variables`; the source posted two template sources to a
  `/admin/templates/validate` route that does not exist.
- `templates.reprovision` sends the `only_active` and `dry_run` options the API
  expects.
- `DomainStatus_` reads the failure reason from the `error` field the status
  endpoint returns (it only looked at `error_message`, so
  `wait_for_active` reported `None`).
- `SSEEvent.from_dict` also accepts the flat items of the history endpoint
  (`type`, `step`, `message`, `timestamp`).
- The `AsyncCustomDomainClient` docstring example uses `create_domain`.
- The async client raised the base error for every failure and could not update,
  verify or provision a domain: it now shares the error mapping and has the
  missing methods. `DomainStatus` knew neither `expired` nor `deprovisioning`.
- `templates.create` sent no `slug`, which the API requires, and a never-honoured
  `is_default`; it now takes `slug` first and an optional `client_id` (owner).
  `Template` carries `slug` and `client_id`.
- `domains.delete` returns the answer of the (now asynchronous) endpoint instead
  of `None`. The example at the bottom of the module reads its URL and token from
  `CUSTOM_DOMAIN_URL` and `CUSTOM_DOMAIN_TOKEN` instead of defaulting to a local
  URL and a dummy token.

## How it is tested

- pytest: `test_client.py` covers the dataclasses, the error mapping, the token
  refresh, every method of the four namespaces with `_request` mocked,
  `wait_for_active`, SSE parsing, the async client (including the typed errors
  and the lifecycle methods) and the asynchronous `delete`.
- behave: `features/python_sdk.feature` points the SDK at the real application
  running in-process (a transport bridges the synchronous httpx client to the
  ASGI app) with an in-memory database and a fake auth server: registering and
  reading a domain, status filtering, lookup, the five error classes, waiting
  for an active and for a failed domain, token refresh, the admin namespaces,
  the asynchronous deletion up to the `NotFoundError`, and the async client
  (list, verify, provision and typed errors).
