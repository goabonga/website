# Onboarding a SaaS application

The service is shared: several applications ("clients": the knowledge base, a
customer portal, ...) let their own customers bring their domain names, and each one
is isolated from the others. This page lists what has to exist, in order, for a new
application to use it, and how it then talks to the service. It only repeats what the
other pages implement; follow the links for the details.

## What each application gets

- Its own **authorized client**: the registry row that says which OAuth2 client may
  create domains and with which defaults (upstream, CNAME target, template, quota,
  webhook). The row is checked on every call, so deactivating it cuts the
  application off immediately.
- **Isolation**: it only lists, reads, updates, deletes and looks up its own domains
  (`403`/`404` otherwise, `lookup` included); it can only use the shared nginx
  templates and the ones an administrator created for it.
- A domain name can only be registered once across all applications (`409`), which is
  what DNS requires.

## 1. An OAuth2 client for the application

On the OAuth2 server of the platform, create a confidential client for the
application (client credentials grant) and grant it the scopes it needs:

| Scope | Needed for |
| --- | --- |
| `custom-domain:read` | Listing and reading domains, status, events, the available templates |
| `custom-domain:write` | Registering, updating, deleting domains; restarting verification and provisioning |
| `custom-domain:lookup` | Resolving a host name to its owner (only if the application wants to) |

Never give an application the administration scope (`ADMIN_SCOPE`): it crosses client
boundaries. Tokens are validated as described in the OAuth2 authentication page; the
`client_id` claim of the token is what is matched against the registry, so the
authorized client must use exactly the OAuth2 `client_id`.

## 2. An authorized client in the service

An operator with the administration scopes registers the application, with the API
(`POST /api/v1/admin/clients`, or `clients.create` in the SDK) or on the host:

```bash
custom-domain create-client \
    --client-id my-app --name "My app" \
    --upstream 10.0.0.5:8000 \
    --cname apps.example.com \
    --max-domains 100 \
    --webhook-url https://my-app.example.com/hooks/custom-domain
# the webhook secret comes from the environment: CUSTOM_DOMAIN_WEBHOOK_SECRET
```

| Field | What to decide |
| --- | --- |
| `--upstream` | Where nginx forwards the requests: a socket path (`/run/my-app/my-app.sock`) or `host:port` (TCP upstream targets page). A domain can override it. |
| `--cname` | The name customers point their CNAME record at, for example `apps.example.com`; it must resolve to the nginx host. DNS is not managed by the service. A domain can override it, and `DEFAULT_CNAME_TARGET` is the fallback when the client has none. |
| `--max-domains` | The quota of live domains (omit for no limit). |
| `default_nginx_template_id` | Optional branded template, created for the client by an administrator (template ownership page). |
| webhook | Optional; see step 4. |

Nothing in the service is specific to one application: no identifier, quota, CNAME
or upstream is built in, they all come from this registry, the request or a setting.

## 3. Reachability

- The upstream must be reachable from the nginx host, and for a Unix socket the nginx
  user must be allowed to open it (group membership on the application's socket
  directory).
- The CNAME target must resolve to the host that runs nginx, with ports 80 and 443
  open: the HTTP-01 challenge of the certificate request is answered there.
- The worker host needs the privileged helper and its sudoers rules (deployment
  page); the application does not.

## 4. Using the service from the application

With the SDK (`custom_domain.client`), using a token obtained with the client
credentials grant:

```python
from custom_domain.client import CustomDomainClient, NotFoundError, construct_event

with CustomDomainClient(CUSTOM_DOMAIN_URL, access_token=token) as service:
    # a customer adds a domain
    created = service.domains.create(
        domain="docs.customer.example", owner_id=str(org.id), owner_type="organization"
    )
    show_to_customer(created.dns_instructions)       # "Create a CNAME record ..."

    # follow it: poll ...
    status = service.domains.get_status(created.id)
    # ... or wait / stream
    service.domains.wait_for_active(created.id, timeout=900)

    # change the upstream, restart a step, remove it
    service.domains.update(created.id, upstream_target="10.0.0.6:8000")
    service.domains.verify(created.id)               # after the customer fixed DNS
    service.domains.delete(created.id)               # asynchronous: poll until NotFoundError
```

`owner_id` and `owner_type` are the application's own identifiers (organization,
tenant, ...); they are returned by `lookup` and in webhooks, which is how the
application maps a host name back to a tenant if it routes by host. An application
that already resolves the host from its own tables does not need `lookup`.

Instead of polling, use the **webhook** of step 2: the service POSTs
`domain.status_changed`, `domain.active`, `domain.failed` and `domain.deleted`
notifications, signed with the shared secret, and the application checks them with
`construct_event(raw_body, signature_header, secret)` (client status webhooks page).
Keep the polling path anyway as a safety net: a notification can be lost after its
retries.

What the SDK covers, in one place: register (`create`), restart verification
(`verify`) and provisioning (`provision`), read the state (`get`, `get_status`,
`get_event_history`, `stream_events`, `wait_for_active`), `list`, `update`, `delete`
(asynchronous), `lookup`, `list_available_templates`, and the webhook helpers; the
async client has the same domain operations.

## 5. Replacing an application's own implementation

An application that manages custom domains itself (nginx files, certbot, DNS checks)
moves to the service in this order:

1. Register the authorized client and the OAuth2 scopes (steps 1 and 2).
2. Re-register the live domains through `POST /domains`. A domain that already has
   a certificate and an nginx file written by the application must not be served by
   both writers: the file name is `<NGINX_CONFIG_PREFIX><domain>.conf`, so choose a
   prefix that differs from the application's, or remove the application's file in
   the same maintenance window.
3. Switch the application's registration, status and deletion code to the SDK and
   the webhook; keep its own plan or entitlement checks (the service has only a
   quota).
4. Remove the application's nginx and certbot code, and the sudoers rules and
   environment it needed for them.

## Checklist

- [ ] OAuth2 client created, scopes granted, no administration scope.
- [ ] Authorized client registered with upstream, CNAME target and quota.
- [ ] Upstream reachable from nginx; CNAME target resolves to the nginx host.
- [ ] Webhook URL (https) and secret set, receiver verifies signatures and is idempotent.
- [ ] Worker has the queue, the helper and the sudoers rules (deployment page).

## Not verified

This page describes the behaviour of the code and its tests. The interaction with a
real OAuth2 server, a real nginx and Let's Encrypt, and the migration of an existing
application's domains, have not been exercised.
