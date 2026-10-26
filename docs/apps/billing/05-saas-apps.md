# SaaS applications

A SaaS application is a tenant of the billing platform. Everything else
(products, prices, customers, subscriptions, usage) belongs to exactly one
SaaS application, and its identifier is written into the metadata of every
Stripe object.

## Endpoints

All routes live under `/platform/saas`.

| Path | Method | Scope | Purpose |
|------|--------|-------|---------|
| `/platform/saas` | POST | `billing:platform:write` | Create a SaaS application (`201`) |
| `/platform/saas` | GET | `billing:platform:read` | List SaaS applications, newest first |
| `/platform/saas/{saas_id}` | GET | `billing:platform:read` | Read one SaaS application |
| `/platform/saas/{saas_id}` | PATCH | `billing:platform:write` | Update fields that are sent |
| `/platform/saas/{saas_id}/sync-stripe` | POST | `billing:platform:write` | Push catalog records with placeholder ids to Stripe |

The API is internal: in production it is only reachable from the VPN subnet
or through the Unix socket.

### Creating an application

```json
{
  "name": "Example App",
  "slug": "example-app",
  "description": "Optional text",
  "webhook_url": "https://app.example.test/billing/events",
  "webhook_secret": "optional signing secret",
  "branding": {"locale": "fr"},
  "checkout_url_allowlist": ["https://app.example.test"]
}
```

- `slug` must match `^[a-z0-9-]+$` (1 to 100 characters) and be unique; a
  duplicate gives `409`.
- `webhook_url` and `webhook_secret` configure the notifications sent to the
  tenant when its subscriptions change (see the webhooks feature). The
  secret is never returned by the API.
- `branding` is free-form JSON. The checkout feature reads `locale` (the
  language of the Stripe Checkout page) and `custom_text` (the Stripe
  `custom_text` block) from it; other keys are stored and returned but not
  interpreted.
- `checkout_url_allowlist` lists the URL prefixes the tenant accepts as
  checkout `success_url` and `cancel_url` (see the checkout feature). Each
  entry is an absolute `http(s)` URL, an origin optionally followed by a
  path, without credentials, query string or fragment; a trailing `/` is
  removed. Sending `null` on update clears the list. An invalid entry gives
  `422`.
- The update schema accepts the same fields except `slug`, plus `is_active`.
- The list hides inactive applications unless `include_inactive=true`.

### Redirect targets

Stripe sends customers back to URLs chosen by the caller after a Checkout
or a portal session. A tenant accepts only the prefixes of its
`checkout_url_allowlist`; the features that hand such a URL to Stripe check
it with `billing.services.redirects`:

- a prefix covers a URL with the same scheme, host and port whose path is
  the path of the prefix or one of its sub-paths (`https://app.example.test`
  covers the whole origin, `https://app.example.test/billing` covers
  `.../billing` and `.../billing/done` but not `.../billing-other`);
- URLs with credentials, other schemes or another host or port are refused;
- when the tenant has no allow-list, every URL is refused unless
  `REDIRECT_ALLOWLIST_REQUIRED=false`; a tenant that defines a list is always
  held to it.

### Stripe sync

`POST /platform/saas/{saas_id}/sync-stripe` walks the products and prices
of the application. Records whose Stripe identifier does not look like a
real one (`prod_` or `price_` followed by at least 14 alphanumeric
characters) are created on Stripe through the Stripe service and updated
with the real identifiers. Prices without `unit_amount` (custom pricing)
are skipped. The answer counts `products_synced`, `prices_synced`,
`products_skipped`, `prices_skipped` and lists `errors`. An unknown
application gives `404`.

## Configuration

| Variable | Default | Purpose |
|----------|---------|---------|
| `REDIRECT_ALLOWLIST_REQUIRED` | `true` | Refuse checkout and portal redirect URLs when the tenant defines no `checkout_url_allowlist` |

## How it is tested

pytest (`apps/billing/tests`):

- `test_schemas_saas_app.py`: slug validation of `SaasAppCreate` and the
  validation and normalization of the checkout URL allow-list;
- `test_services_redirects.py`: prefix matching (origins, segment-aware
  paths, ports, credentials, schemes) and the required/optional policy;
- `test_routes_platform_saas.py`: creation (with an allow-list), duplicate
  slug, listing, read, update, 404 answers, the placeholder id detection and
  the Stripe sync with a mocked Stripe service;
- `conftest.py` gains the `sample_saas_app_data` fixture.

behave (`apps/billing/features/saas_apps.feature`), with an authenticated
client, the in-memory database and the mocked Stripe service:

- Create a SaaS app;
- Create a SaaS app with duplicate slug returns 409;
- List SaaS apps;
- Get a SaaS app by ID;
- Update a SaaS app;
- Get a non-existent SaaS app returns 404;
- Sync a SaaS app without products to Stripe;
- A SaaS app stores its checkout URL allow-list;
- An invalid checkout URL allow-list entry is rejected.
