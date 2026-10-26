# Stripe service

`billing.services.stripe_service.StripeService` is the single place where
the Stripe SDK is called. It enforces the multi-tenant rule of the platform:
every object it creates carries `metadata.saas_id`, so each tenant only sees
its own products, prices, customers and subscriptions in the shared Stripe
account. The routes of the next features obtain the service through
`get_stripe_service()`, a cached factory that makes tests easy to patch.

## Operations

| Area | Methods |
|------|---------|
| Products | `create_product`, `update_product`, `get_product` |
| Prices | `create_price`, `update_price`, `get_price` |
| Customers | `create_customer`, `update_customer`, `get_customer`, `create_customer_portal_session` |
| Subscriptions | `create_subscription`, `update_subscription`, `cancel_subscription`, `get_subscription`, `preview_subscription_upgrade`, `upgrade_subscription` |
| Checkout | `create_checkout_session` |
| Usage | `report_usage` |
| Webhooks | `verify_webhook_signature` |

Behaviours worth knowing:

- Creation methods merge caller-provided `metadata` with `saas_id`
  (customers also get `external_id`). The server-owned keys are written
  last and the same keys are stripped from caller metadata, so a caller can
  never override `saas_id` (or forge `external_id`): this also holds for
  the metadata of Checkout sessions and for the update methods, which merge
  metadata on the Stripe side.
- Stripe metadata only holds strings (50 keys, 40 characters per key, 500
  per value). `to_stripe_metadata` serializes non-string values, such as the
  `features` and `limits` documents of a plan, to compact JSON, drops `None`
  values and skips, with a warning, the entries Stripe would refuse; the
  complete document stays in the local database.
- `create_price` uses `DEFAULT_CURRENCY` and `DEFAULT_RECURRING_INTERVAL`
  when the caller gives none.
- `create_checkout_session` accepts an optional `locale` and `custom_text`
  that are forwarded to Stripe untouched (the checkout feature fills them
  from the tenant branding).
- Recurring prices carry the interval, interval count and `usage_type`;
  metered prices omit `unit_amount` and aggregate usage with `sum`;
  one-time prices only carry the amount.
- `build_stripe_description(description, extra_data)` appends the enabled
  entries of `extra_data["features"]` to the product description as a
  bullet list; features flagged `disabled` are left out.
- `verify_webhook_signature` uses `STRIPE_WEBHOOK_SECRET` unless a secret is
  passed.
- `report_usage` always sends `action="increment"` and forwards the
  idempotency key to Stripe when given.

## Configuration

| Variable | Default | Purpose |
|----------|---------|---------|
| `STRIPE_SECRET_KEY` | empty | Stripe API key (secret) |
| `STRIPE_PUBLISHABLE_KEY` | empty | Stripe publishable key |
| `STRIPE_WEBHOOK_SECRET` | empty | Webhook signing secret (secret) |
| `DEFAULT_RECURRING_INTERVAL` | `month` | Interval of a recurring price that gives none (`day`, `week`, `month`, `year`) |

`STRIPE_SECRET_KEY` and `STRIPE_WEBHOOK_SECRET` are first looked up as
systemd credentials in `$CREDENTIALS_DIRECTORY`, then in the environment.

The `stripe` dependency is capped below version 15: that release removed the
dict-style `.get()` accessor on Stripe objects, which the webhook and
subscription code relies on.

## How it is tested

pytest (`apps/billing/tests`):

- `test_services_stripe.py`: every method with the Stripe SDK mocked,
  metadata injection, non-overridable `saas_id`, stringification of nested
  metadata, price parameters and defaults, description building, factory
  caching;
- `test_config.py` covers the Stripe settings and credentials.

behave (`apps/billing/features/stripe_service.feature`), using the real
`StripeService` class with the SDK entry points replaced by mocks, so no
network call is made:

- Products are tagged with the SaaS identifier;
- Custom metadata is merged with the SaaS identifier;
- Callers cannot override the SaaS identifier;
- Checkout metadata cannot override the SaaS identifier;
- Nested metadata is sent to Stripe as strings;
- Customers carry the SaaS identifier and the external identifier;
- Metered prices are summed over the billing period;
- Enabled features are appended to the product description.

From this feature on the behave environment replaces `get_stripe_service`
with a mock in every module that imports it.
