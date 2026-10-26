# Knowledge as a client of the platform services

Knowledge does not send emails, serve customer domains or hold the plans itself: it is a
client of the platform's **mailler**, **custom-domain** and **billing** services, which are
shared with the other applications of the platform and keep their clients apart. This page
is the checklist for an operator who deploys knowledge: what to create in each service, with
which scopes, and the settings that connect them. Each service has its own onboarding page
(mailler: *Onboarding an application*, custom-domain: *Onboarding a SaaS application*, billing:
*Client partitioning*); this one only lists what is specific to knowledge. No identifier below is
built into the code: every name is a value you choose and put in the settings.

## 1. The OAuth2 client

On the OAuth2 server, create a confidential client for the backend of knowledge (client
credentials grant) and grant it exactly these scopes, and no administration scope:

| Service | Scopes | Used for |
| --- | --- | --- |
| mailler | `mailler:send` | Sending the five emails (`POST /api/v1/send`) |
| custom-domain | `custom-domain:read`, `custom-domain:write` | Registering, reading, verifying and deleting domains |
| billing | `billing:platform:read`, `billing:platform:write`, `billing:checkout:write` | Plans, subscriptions (read, upgrade, cancel, reactivate) and checkout |

The services identify the application by the `client_id` of the token, so register that same
identifier in each of them. One client can serve the three services (it is then
`OAUTH2_CLIENT_ID`/`OAUTH2_CLIENT_SECRET`); to give each service its own client set
`MAILLER_CLIENT_ID`, `CUSTOM_DOMAIN_CLIENT_ID` and `BILLING_CLIENT_ID` with their secrets. The
secrets are systemd credentials or variables (`*_CLIENT_SECRET`).

## 2. Mailler

On the mailler host, with the `mailler` command (it talks to the database), register the client
with the sender and the provider knowledge is allowed to use, then import the templates:

```bash
mailler clients register <client id> --name "Knowledge" \
    --from-email <sender address> --from-name "<sender name>" \
    --allowed-provider <provider> --default-provider <provider> \
    --daily-quota <n> --rate-limit-per-minute <n>

mailler templates import --client-id <client id> "$(python -m knowledge.email_templates)"
```

The sender address and name, the provider and the quotas are decided here, in mailler; knowledge
sets none of them. Run the import again at every deployment (it creates or updates). Set
`MAILLER_URL` (or `MAILLER_SOCKET_PATH`, with the service user in the group of the socket).
A `403` in the worker log means the client is not registered or is deactivated, a `404` that the
templates were not imported, a `429` that the rate limit or the quota is reached.

## 3. Custom-domain

On the custom-domain host register the application with its upstream and CNAME target, and the
URL that receives the status webhooks. The webhook secret (at least 32 characters) comes from the
environment of the command, and is the same value as `CUSTOM_DOMAIN_WEBHOOK_SECRET` of knowledge:

```bash
export CUSTOM_DOMAIN_WEBHOOK_SECRET=<secret>
custom-domain create-client --client-id <client id> --name "Knowledge" \
    --upstream /run/knowledge/knowledge.sock \
    --cname <host your customers point their CNAME at> \
    --max-domains <n> \
    --webhook-url https://<knowledge host>/webhooks/custom-domain
```

The upstream is the socket (or `host:port`) that nginx forwards to; the nginx user must be
allowed to open it. The CNAME target must resolve to the nginx host with ports 80 and 443 open.
Set `CUSTOM_DOMAIN_SERVICE_URL` (or `CUSTOM_DOMAIN_SERVICE_SOCKET_PATH`), `CUSTOM_DOMAIN_WEBHOOK_SECRET`
and `CUSTOM_DOMAIN_CNAME_TARGET` (the same CNAME, shown before a domain is registered). To move
domains that knowledge configured itself, see *Moving an existing installation* on the
[custom domains](13-custom-domains.md) page.

## 4. Billing

With the administration scope (or the `billing-admin` command on the billing host) create the
SaaS application with the URLs Stripe may send customers back to, bind the client, and set the
webhook:

```bash
billing-admin saas create --name "Knowledge" --slug <slug> \
    --checkout-url <origin of knowledge, e.g. https://knowledge.example.com>
billing-admin client bind --saas <slug> --client-id <client id>
```

Then set `webhook_url` (`https://<knowledge host>/webhooks/billing`) and `webhook_secret` on the
application (API or admin interface); the secret is `BILLING_WEBHOOK_SECRET` of knowledge. Create the
products with a `slug` that is one of the plans of the application (`free`, `starter`, `pro`,
`enterprise`: the names of `PlanType`) and, in their metadata, the `limits` that the
[quotas](07-quotas.md) enforce (`max_collections`, `max_documents_per_collection`,
`max_total_documents`, `max_api_calls_per_month`, `max_storage_bytes`; `-1` is unlimited), the
`features` shown on the pricing pages, then the prices. The settings are `BILLING_API_URL` (or
the socket), `BILLING_APP_SLUG` (the slug), `BILLING_SAAS_ID` (the identifier returned by billing, no
default), `BILLING_CHECKOUT_SUCCESS_URL` and `BILLING_CHECKOUT_CANCEL_URL` (inside the
allow-list). Define `QUOTA_FALLBACK_LIMITS` for the outages ([plan limits](09a-plan-limits.md)).

## Checklist

- [ ] OAuth2 client created with the scopes above, no administration scope.
- [ ] Client registered in mailler with sender, provider and quotas; templates imported.
- [ ] Authorized client registered in custom-domain with upstream, CNAME, quota and webhook URL.
- [ ] SaaS application created in billing, client bound, allow-list and webhook set, plans and limits created.
- [ ] `BILLING_SAAS_ID`, `BILLING_WEBHOOK_SECRET`, `CUSTOM_DOMAIN_WEBHOOK_SECRET` set: without them the
      webhooks answer `503`.
- [ ] `OPERATOR_NAME`, the contact addresses and `SUPPORT_URL` set (empty values are left out of the pages).

## Not verified

The commands above are those documented by the three services; they were not run against real
services, a real OAuth2 server, Stripe, a provider or nginx. The exchanges of knowledge with them
are exercised with mocked HTTP only.
