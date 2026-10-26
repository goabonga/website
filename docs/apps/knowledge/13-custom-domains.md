# Custom domains

Organizations on the Enterprise plan can serve their workspace on their own domain (for
example `docs.acme.example`). The application keeps what is its own business: the plan that
allows it, the format of the name and the table that maps a host name to a workspace, which
the [multi-tenant middleware](08-multi-tenancy.md) reads. Everything that touches the
infrastructure is delegated to the platform's **custom-domain** service: it checks the DNS,
obtains and renews the certificate, writes the web server configuration and removes it. The
application has no nginx, certbot, DNS or `sudo` code, and its workers need none of them.

## How it works

1. The customer enters a domain. The application validates the format, checks that the
   plan allows custom domains and that no other workspace uses the name, then **registers**
   the domain in the service (`POST /api/v1/domains`, `owner_id` = the workspace id,
   `owner_type` = `organization`). The upstream, the CNAME target and the quota come from the
   registration of the application's OAuth2 client in the service, not from this application.
2. The service answers with the id of the domain and the CNAME target; both are stored on the
   workspace (`custom_domain_service_id`, `custom_domain_cname_target`) and the customer is
   told which CNAME record to create.
3. The service verifies the DNS, provisions the certificate and the web server, and tells the
   application each status change with a **signed webhook**. The webhook updates the
   `custom_domain_*` columns. The domain is only used to resolve tenants once it is `active`.
4. A periodic task **reconciles** by polling, so that a lost notification does not leave a
   domain stuck.
5. Removing the domain asks the service to delete it (asynchronous on its side) and the
   workspace forgets the name at once.

## Status life cycle

`CustomDomainStatus` is the status of the service, with three of its statuses folded:

| Status | Meaning |
| --- | --- |
| `pending` | Registered, DNS not verified yet. |
| `dns_verifying` | A verification is running. |
| `dns_verified` | The CNAME points to the platform. |
| `ssl_provisioning` | The certificate and the web server are being set up. |
| `active` | Fully provisioned; only now is the domain used for tenant resolution. |
| `failed` | A step failed (also `suspended` and `expired` in the service); the reason is stored on the workspace. |

`deprovisioning` (the domain is being removed) is not recorded: the application waits for
`domain.deleted`.

## Service functions

`knowledge.services.custom_domain`:

- `validate_domain(domain)`: format (hostname labels, at most 253 characters) and reserved names
  (`localhost`, `127.0.0.1`, `0.0.0.0`, `*.local`). The service validates the name too; this
  check gives the customer an answer without a call.
- `map_status(status)`, `apply_status(organization, status, error, when)` and
  `clear_domain(organization)`: the single place that turns a status of the service into the
  columns of the workspace, used by both the webhooks and the reconciliation so that the two
  give the same result.
- `CustomDomainClient`, a thin asynchronous client written against the HTTP API of the service
  (no dependency on its code), over `CUSTOM_DOMAIN_SERVICE_URL` or the Unix socket
  `CUSTOM_DOMAIN_SERVICE_SOCKET_PATH`. A connection is opened per call, so the client works in
  the web routes and in the Celery tasks alike:

| Method | Service call | OAuth2 scope |
| --- | --- | --- |
| `register(domain, owner_id, metadata)` | `POST /api/v1/domains` | `custom-domain:write` |
| `get(domain_id)` | `GET /api/v1/domains/{id}` (`None` on `404`) | `custom-domain:read` |
| `verify(domain_id)` | `POST /api/v1/domains/{id}/verify` | `custom-domain:write` |
| `delete(domain_id)` | `DELETE /api/v1/domains/{id}` (`False` on `404`) | `custom-domain:write` |
| `list_domains(owner_id, limit)` | `GET /api/v1/domains` | `custom-domain:read` |

The token is obtained with the OAuth2 client-credentials grant
(`knowledge.services.service_auth`): `CUSTOM_DOMAIN_CLIENT_ID`/`CUSTOM_DOMAIN_CLIENT_SECRET`, or
the application's confidential client when those are empty. The service identifies the
application by the `client_id` of the token, so this client must be the one registered there.
Errors raise `CustomDomainError(detail, status_code, retryable)`: `409` the name is already
registered (by another application or workspace), `403` the client is not authorized or its
quota is reached, `400` the service refuses the name, `5xx`/`429`/network failures are
retryable.

## Status webhooks

`POST /webhooks/custom-domain` (internal sub-application) receives
`domain.status_changed`, `domain.active`, `domain.failed` and `domain.deleted`. The URL and
the secret are set on the authorized client of the application in the service
(`custom-domain create-client --webhook-url ...`).

- **No secret, no webhook.** While `CUSTOM_DOMAIN_WEBHOOK_SECRET` is empty everything is
  refused with `503`.
- **Signature.** `X-Custom-Domain-Signature` is `t=<unix time>,v1=<hex>`, the HMAC-SHA256 of
  `<t>.<raw body>` with the secret, compared in constant time on the raw bytes. Several `v1`
  values are accepted (secret rotation). A missing, malformed or wrong signature is a `401`.
- **Replay.** A request whose signed time is further than `CUSTOM_DOMAIN_WEBHOOK_TOLERANCE`
  seconds (300) from now is refused, and the delivery id (`id` of the body, or the
  `X-Custom-Domain-Delivery` header) is recorded in Redis for `CUSTOM_DOMAIN_EVENT_TTL` seconds
  once the change is committed: a repeated delivery answers `{"status": "duplicate"}`. A delivery
  that failed is not recorded, so the service's retry is processed.
- **Effect.** The workspace is found by the service id (or, for a domain registered before the
  id was stored, by name and owner id). The status of the `domain` snapshot of the request is
  applied (it is the current status, so deliveries out of order are harmless), with its `error`
  for a failure. `domain.deleted` clears the domain if the id is still the workspace's. An
  unknown workspace is answered `{"status": "unknown"}` (the customer removed the domain
  meanwhile), other events `{"status": "ignored"}`.

## Reconciliation

`knowledge.tasks.custom_domain.reconcile_custom_domains`, a beat task every
`CUSTOM_DOMAIN_RECONCILE_INTERVAL` seconds (300), does nothing when the service is not
configured. For the workspaces that have a domain it:

- **registers** the domains that have no service id: this is how the domains that the
  application configured itself before using the service are moved to it (see below);
- **reads** the domains that are `pending`, `dns_verifying`, `dns_verified` or `ssl_provisioning`
  and applies the status. `active` and `failed` domains are left to the webhooks;
- a domain the service no longer knows becomes `failed` with a message and loses its service id
  (the customer registers it again); a name registered by someone else (`409`) becomes `failed`
  with the reason; an unreachable service is counted and tried again next time.

Each workspace has its own transaction. The task returns
`{"registered", "updated", "failed", "errors"}`.

## Data model

Alembic revision `009_custom_domain_service` adds `tenants.custom_domain_service_id` (unique)
and `tenants.custom_domain_cname_target`, both nullable.

## Moving an existing installation

Before this feature the application wrote the nginx files and ran certbot itself. After
upgrading, the first reconciliation registers every existing domain in the service. Two writers
must not serve the same name: give the service a file prefix that differs from the old
`custom-domain-` files of the application (`NGINX_CONFIG_PREFIX` of the service), or remove the
old files in the same maintenance window, and remove the nginx/certbot sudoers rules and
settings of the application's worker. Every setting that configured nginx, certbot or the
upstream socket was removed (`CUSTOM_DOMAIN_NGINX_*`, `CUSTOM_DOMAIN_CERTBOT_*`,
`CUSTOM_DOMAIN_UPSTREAM_SOCKET`, `CUSTOM_DOMAIN_ENABLED`,
`CUSTOM_DOMAIN_DNS_CHECK_INTERVAL_MINUTES`), as was the `dnspython` dependency.

## Settings

| Variable | Default | Description |
| --- | --- | --- |
| `CUSTOM_DOMAIN_SERVICE_URL` | empty | HTTP base URL of the custom-domain service. |
| `CUSTOM_DOMAIN_SERVICE_SOCKET_PATH` | empty | Unix socket of the service; takes precedence over the URL. |
| `CUSTOM_DOMAIN_CLIENT_ID` | empty | OAuth2 client registered in the service; empty means `OAUTH2_CLIENT_ID`. |
| `CUSTOM_DOMAIN_CLIENT_SECRET` | empty | Its secret (a secret); empty means `OAUTH2_CLIENT_SECRET`. |
| `CUSTOM_DOMAIN_CNAME_TARGET` | empty | CNAME shown to the customer before a domain is registered; after registration the target given by the service is used. It must be the CNAME of the client's registration in the service. |
| `CUSTOM_DOMAIN_WEBHOOK_SECRET` | empty | Secret that signs the status webhooks (a secret). Required: without it the webhook answers `503`. |
| `CUSTOM_DOMAIN_WEBHOOK_TOLERANCE` | `300` | Seconds a signed timestamp may differ from now. |
| `CUSTOM_DOMAIN_EVENT_TTL` | `604800` | Seconds a processed delivery id is remembered. |
| `CUSTOM_DOMAIN_RECONCILE_INTERVAL` | `300.0` | Seconds between two reconciliation passes. |
| `SERVICE_TIMEOUT` | `10.0` | Seconds before a call to the service times out. |

## Tests

pytest:

- `unit/test_custom_domain.py`: domain validation, the mapping and application of statuses,
  and the service client (request on the wire, scopes, refusals and their retryable flag,
  token renewal and failures, `404` handling).
- `unit/test_tasks_custom_domain.py`: the reconciliation (registration, refresh, lost and
  conflicting domains, unreachable service, isolation between workspaces, the selection of
  the workspaces) and the task.
- `unit/test_custom_domain_webhooks.py`: the signature (rotation, tolerance, tampering), the
  application of each event and the route (secret, signature, replay, duplicates, failures).
- `unit/test_migrations.py`: revision `009` on SQLite, up and down.
- `unit/test_celery_config.py`: the beat entry.

behave (`features/custom_domains.feature`), with the service as a mocked transport:

- Domain validation (outline: accepted and rejected names)
- Statuses of the custom-domain service (outline)
- A domain is registered in the service for a workspace
- The service refuses a name that is already registered
- The service is not configured
- The verification of a domain is restarted
- A domain is removed from the service
- Deleting a domain the service forgot is not an error
- A signed notification activates the domain
- A failure notification carries the reason
- A deletion notification forgets the domain
- A delivery is applied once
- A captured notification cannot be played back later
- A forged notification is refused
- Notifications are refused until a secret is configured
- The reconciliation registers the domains the service does not know
- The reconciliation refreshes the domains being set up

Not verified: a real custom-domain service, DNS, certificates or nginx; the migration on
PostgreSQL.
