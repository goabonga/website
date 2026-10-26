# Checkout

The checkout endpoint creates a Stripe Checkout session so that a customer
can pay for a subscription or a one-time purchase on the page hosted by
Stripe. The tenant redirects the user to the returned URL.

## Endpoint

| Path | Method | Scope | Purpose |
|------|--------|-------|---------|
| `/checkout/session` | POST | `billing:checkout:write` | Create a Checkout session |

### Request

```json
{
  "saas_id": "<internal tenant id>",
  "external_id": "user-42",
  "price_id": "<internal price id>",
  "success_url": "https://app.example.test/billing/success",
  "cancel_url": "https://app.example.test/billing/cancel",
  "mode": "subscription",
  "quantity": 1,
  "trial_period_days": 14,
  "metadata": {},
  "customer_email": "user@example.test",
  "customer_name": "Ada"
}
```

| Field | Rules |
|-------|-------|
| `saas_id`, `price_id` | Internal identifiers, required |
| `customer_id` / `external_id` | Identify the customer, either the internal id or the tenant's external id |
| `success_url`, `cancel_url` | Valid HTTP(S) URLs, required, and covered by the `checkout_url_allowlist` of the tenant (`422` otherwise) |
| `mode` | `subscription` (default) or `payment` |
| `quantity` | 1 to `CHECKOUT_MAX_QUANTITY`, default 1 |
| `trial_period_days` | 0 to `MAX_TRIAL_PERIOD_DAYS` |
| `metadata` | Free-form, sent to Stripe as strings; `saas_id` cannot be overridden |
| `customer_email`, `customer_name` | Used to create the customer on the fly |

How the customer is resolved:

1. With `customer_id`, or with `external_id`, the customer must belong to
   the tenant and must not be soft deleted.
2. With an `external_id` that does not exist yet and a `customer_email`,
   the customer is created in Stripe and in the database before the
   session is created.
3. Otherwise the answer is `404 Customer not found...`.

An unknown tenant gives `404 SaaS app not found`. The price must be an
active price of a product of the same tenant as `saas_id`: a price that does
not exist, is inactive or belongs to another tenant gives `404 Price not
found` (the answer does not tell which). Together with the customer lookup
this means a session can never mix a customer of one tenant with a price of
another one. The Stripe session is created with the Stripe customer id and
the Stripe price id and the answer is:

```json
{"session_id": "cs_...", "url": "https://checkout.stripe.com/..."}
```

The subscription itself is created locally when Stripe reports the
completed session through the webhook feature.

### Redirect targets

Stripe redirects the customer to `success_url` or `cancel_url`, so they are
checked against the `checkout_url_allowlist` of the tenant (see the SaaS
applications page): a prefix covers the URLs of its origin and path. A URL
outside the list gives `422` and Stripe is not called. A tenant with no list
is refused as well, unless `REDIRECT_ALLOWLIST_REQUIRED=false`.

### Server-owned metadata

The session, and the subscription it creates, carry `metadata.saas_id`,
which the webhook feature uses to route Stripe events back to the tenant.
The value is set by the server after the caller's `metadata` is applied, and
a `saas_id` or `external_id` key sent by the caller is dropped, so a client
cannot reroute its session to another tenant.

### Branding

The `branding` of the tenant customizes the hosted page: `branding.locale`
(a string such as `fr`) becomes the Stripe `locale` and `branding.custom_text`
(an object) the Stripe `custom_text` block. Values of another type are
ignored; other branding keys are not used by the checkout.

## Configuration

| Variable | Default | Purpose |
|----------|---------|---------|
| `CHECKOUT_MAX_QUANTITY` | `1000` | Upper bound of `quantity` |
| `MAX_TRIAL_PERIOD_DAYS` | `730` | Upper bound of `trial_period_days` (introduced with the subscriptions) |
| `REDIRECT_ALLOWLIST_REQUIRED` | `true` | Refuse the URLs of a tenant that has no allow-list (introduced with the SaaS applications) |

## How it is tested

pytest (`apps/billing/tests/test_routes_checkout.py`):
`TestCreateCheckoutSession` (customer by id or external id, automatic
customer creation, missing customer, missing price, missing tenant),
`TestCheckoutIsolation` (price query scoped to the tenant, foreign price,
`saas_id` metadata that cannot be overridden through the real Stripe
service), `TestCheckoutRedirects`, `TestCheckoutBranding` and
`TestCheckoutBounds`, with a mocked database session and Stripe service.

behave (`apps/billing/features/checkout.feature`):

- Create a checkout session with customer_id;
- Create a checkout session with external_id;
- Auto-create customer during checkout;
- Checkout with non-existent customer returns 404;
- Checkout with non-existent price returns 404;
- Checkout with a price of another SaaS app returns 404;
- Checkout metadata cannot override the SaaS identifier;
- Checkout with a success URL outside the allow-list returns 422;
- Checkout for a SaaS app without allow-list returns 422;
- The SaaS app branding customizes the hosted page.
