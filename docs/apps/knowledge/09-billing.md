# Billing integration

Subscriptions and prices are managed by the platform billing service, which is shared
by several SaaS applications: each one is a tenant of billing with its own plans,
customers and subscriptions, and an OAuth2 client can only act on the applications it
is bound to (see the billing client partitioning page). The knowledge service talks to
billing in two directions: it reads plans and drives the subscription life cycle
through `BillingClient`, and it receives subscription events on a webhook to keep each
organization's plan in sync. Nothing about the billing tenant is built into the code:
the identifier, the slug, the secrets and the redirect URLs are settings, and
the onboarding of the application as a client of billing is described on the
platform onboarding page.

## Billing client

`knowledge.services.billing.BillingClient` is an asynchronous client for the
billing API. It connects either over HTTP (`BILLING_API_URL`) or over a Unix
socket (`BILLING_SOCKET_PATH`, which takes precedence); `is_configured` is
false when neither is set and `get_plans()` then returns an empty list.
`BILLING_SAAS_ID` has no default: a call that needs it (checkout, subscriptions)
raises `BillingAPIError("BILLING_SAAS_ID is not configured")` until it is set.

| Method | Billing API call | OAuth2 scope requested |
| --- | --- | --- |
| `get_plans()` / `get_plan_by_slug()` | `GET /plans/{app_slug}` | `billing:platform:read` |
| `create_checkout_session(...)` | `POST /checkout/session` | `billing:checkout:write` |
| `get_tenant_subscription(tenant_id)` | `GET /platform/{saas_id}/external/{tenant_id}/subscription` | `billing:platform:read` |
| `preview_upgrade(...)` | `POST /platform/{saas_id}/subscriptions/{id}/upgrade/preview` | `billing:platform:read` |
| `upgrade_subscription(...)` | `POST /platform/{saas_id}/subscriptions/{id}/upgrade` | `billing:platform:write` |
| `cancel_subscription(...)` | `POST /platform/{saas_id}/subscriptions/{id}/cancel` | `billing:platform:write` |
| `reactivate_subscription(...)` | `POST /platform/{saas_id}/subscriptions/{id}/reactivate` | `billing:platform:write` |

Every call is authenticated: the plans are not public (billing runs with
`PLANS_PUBLIC=false`), so the client sends a bearer token obtained with the OAuth2
client-credentials grant against `<OAUTH2_ISSUER>/oauth2/token`
(`knowledge.services.service_auth`, shared with the other platform services). The
OAuth2 client is `BILLING_CLIENT_ID`/`BILLING_CLIENT_SECRET`, or the confidential
client of the [authentication](02-authentication.md) feature when those are empty; it
must be bound to this SaaS application in billing, because billing identifies the
caller by the `client_id` of the token. Tokens are cached in memory until 30 seconds
before they expire. Failures are raised as `BillingAPIError`; the answers `409`
(subscription already canceled, or not cancelable/reactivable) and `422` (checkout URLs
outside the allow-list) get an explicit message.

The plan list is cached in Redis for `BILLING_CACHE_TTL` seconds (key
`knowledge:billing:plans:<app_slug>`); a Redis failure only means a cache miss.
The responses are parsed into dataclasses: `Plan` (with `monthly_price`,
`yearly_price`, `yearly_savings_percent`, `yearly_monthly_equivalent`,
`is_free`), `PlanFeature`, `PlanPrice` (`display_amount` renders cents),
`CheckoutSession`, `UpgradePreview`, `UpgradeResult`, `CancelResult`,
`ReactivateResult` and `TenantSubscription`. Plans are sorted by `sort_order`.
`Plan.limits` is a plain `dict[str, int]` (or `None`): the names are those chosen
for the application in billing, and `parse_limits` leaves out entries that are not
integers.

### Checkout redirect URLs

Stripe sends the customer back to a URL that knowledge chooses, and billing only
accepts URLs covered by the `checkout_url_allowlist` of the SaaS application.
`checkout_redirect_urls()` returns the two URLs from `BILLING_CHECKOUT_SUCCESS_URL` and
`BILLING_CHECKOUT_CANCEL_URL` and raises `BillingAPIError` when one is empty; both must
be registered in the allow-list of the application in billing, otherwise the checkout
is refused with `422`.

## Subscription webhook

`POST /webhooks/billing` is served by the internal sub-application (tag
`Webhooks`, visible in `/internal/docs`). The URL and the secret are registered on the
SaaS application in billing (`webhook_url`, `webhook_secret`).

- **The signature is mandatory.** The `X-Billing-Signature` header must carry the
  hexadecimal HMAC-SHA256 of the raw body, compared in constant time; a missing or wrong
  signature is a `401`. When `BILLING_WEBHOOK_SECRET` or `BILLING_SAAS_ID` is empty the
  endpoint refuses everything with `503`: there is no unsigned mode.
- The body is `{"id", "type", "created", "saas_id", "saas_slug", "data"}`; anything else
  (an event without `id` included) is a `400`. An event whose `saas_id` is not
  `BILLING_SAAS_ID` belongs to another application of the shared billing service and is
  refused with `400`.
- **Idempotency.** The event `id` is stable (billing derives it from the Stripe event):
  once an event is processed its id is recorded in Redis for `BILLING_EVENT_TTL` seconds
  and a repeated delivery answers `{"status": "duplicate"}` without touching the
  organization. The id is only recorded after the change is committed, so a failed event
  stays retryable. If Redis is down the event is processed anyway; the handlers set a state
  rather than apply a delta, so processing twice is harmless.
- `data.customer_external_id` is the organization id and `data.plan_slug` is matched with
  `free`, `starter`, `pro` or `enterprise` (the `PlanType` names). The plan is identified
  by its slug, never by `plan_name`, which is a display name that can be renamed.

| Event | Subscription status | Effect |
| --- | --- | --- |
| `subscription.created` / `subscription.updated` | `active`, `trialing` | The organization moves to the plan of `plan_slug` (unknown slugs are logged and ignored). |
| `subscription.created` / `subscription.updated` | `canceled`, `unpaid`, `incomplete_expired` | The organization is downgraded to `free`. |
| `subscription.created` / `subscription.updated` | `past_due` | The plan is kept; a warning is logged. |
| `subscription.deleted` | any | The organization is downgraded to `free`. |
| other | any | Ignored. |

The plan change is committed in its own database session; an unexpected
failure rolls back and answers `500`. An unknown organization is logged and
the call still answers `{"status": "ok"}`.

## Settings

| Variable | Default | Description |
| --- | --- | --- |
| `BILLING_API_URL` | empty | HTTP base URL of the billing API. |
| `BILLING_SOCKET_PATH` | empty | Unix socket of the billing API; preferred over the URL when set. |
| `BILLING_APP_SLUG` | empty | Slug of this SaaS application in billing; the plans are read from `/plans/<slug>`. |
| `BILLING_SAAS_ID` | empty | Identifier of this SaaS application in billing. Required: no default, billing calls and webhooks are refused without it. |
| `BILLING_CLIENT_ID` | empty | OAuth2 client used to call billing; empty means `OAUTH2_CLIENT_ID`. |
| `BILLING_CLIENT_SECRET` | empty | Its secret (a secret, systemd credential or variable); empty means `OAUTH2_CLIENT_SECRET`. |
| `BILLING_CACHE_TTL` | `300` | Seconds the plan list stays cached in Redis. |
| `BILLING_WEBHOOK_SECRET` | empty | Secret that signs the webhooks (a secret). Required: without it the webhook answers `503`. |
| `BILLING_EVENT_TTL` | `604800` | Seconds a processed event id is remembered (one week). |
| `BILLING_CHECKOUT_SUCCESS_URL` | empty | Where Stripe sends the customer after a payment; must be in the allow-list of the application in billing. |
| `BILLING_CHECKOUT_CANCEL_URL` | empty | Where Stripe sends the customer when the checkout is abandoned; idem. |
| `SERVICE_TIMEOUT` | `10.0` | Seconds before a call to billing (or to the token endpoint) times out. |

## Tests

pytest:

- `unit/test_billing_service.py`: dataclass helpers, limits parsing, plan parsing and
  caching, HTTP and Unix-socket transports, the token request, the required SaaS id, the
  checkout redirect URLs and every subscription call with its error handling.
- `unit/test_service_auth.py`: the OAuth2 client of each service and its fallback, the
  token endpoint, the client-credentials request, the token cache and its renewal, and the
  failures.
- `unit/test_event_dedupe.py`: the record of processed events and its Redis failures.
- `test_billing_webhooks.py`: the refusal without secret or SaaS id, signature
  verification, the foreign SaaS, event handling for each status, mapping by plan slug
  (and not by name), idempotency and payload errors.

behave (`features/billing.feature`):

- An active subscription upgrades the organization
- The plan is identified by its slug, not by its name
- A canceled subscription downgrades the organization
- A deleted subscription downgrades the organization
- A past due subscription keeps the current plan
- An unknown plan slug leaves the plan unchanged
- An event is applied once even when billing sends it twice
- An event for another SaaS application is refused
- A bad signature is rejected
- A missing signature is rejected
- A malformed payload is rejected
- Nothing is accepted when no secret is configured
- Nothing is accepted when the SaaS application is not configured
- Plans are fetched from the billing API and sorted
- Plan prices are formatted for display
- Plans are requested with a token for the application slug
- The limits keep the names chosen by the application
- Plans are cached after the first fetch
- A billing API failure is reported
- Without billing configuration there are no plans
- A checkout is created for the configured SaaS application
- A checkout cannot start without a SaaS id

Not verified: no real billing service, OAuth2 server or Redis was used; the HTTP exchanges
are mocked.
