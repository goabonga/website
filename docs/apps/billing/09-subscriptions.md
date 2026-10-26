# Subscriptions

A subscription links a customer to a price. The API keeps the local record
in step with the Stripe subscription: every mutating call goes to Stripe
first, then updates the database.

## Endpoints

All routes live under `/platform/{saas_id}`. A subscription is always looked
up through its customer, so a subscription of another tenant is `404`.

| Path | Method | Scope | Purpose |
|------|--------|-------|---------|
| `/subscriptions` | GET | `billing:platform:read` | List the subscriptions of the tenant |
| `/customers/{customer_id}/subscriptions` | GET | `billing:platform:read` | List the subscriptions of a customer |
| `/customers/{customer_id}/subscriptions` | POST | `billing:platform:write` | Create a subscription (`201`) |
| `/external/{external_id}/subscription` | GET | `billing:platform:read` | Current active or trialing subscription of a customer, by external id |
| `/subscriptions/{subscription_id}` | GET | `billing:platform:read` | Read one subscription |
| `/subscriptions/{subscription_id}` | PATCH | `billing:platform:write` | Change `cancel_at_period_end` or `extra_data` |
| `/subscriptions/{subscription_id}` | DELETE | `billing:platform:write` | Cancel (`immediately=true` for an immediate cancellation) |
| `/subscriptions/{subscription_id}/sync` | POST | `billing:platform:write` | Refresh status, period and item id from Stripe |
| `/subscriptions/{subscription_id}/upgrade/preview` | POST | `billing:platform:read` | Proration preview of a plan change |
| `/subscriptions/{subscription_id}/upgrade` | POST | `billing:platform:write` | Change plan |

### Listing

`GET /subscriptions` accepts `status_filter` (any `SubscriptionStatus`),
`limit` (1 to `LIST_MAX_LIMIT`, default `LIST_DEFAULT_LIMIT`) and `offset`. The external-id lookup
answers `null` when the customer does not exist or has no active or
trialing subscription.

### Creating

```json
{"price_id": "<internal price id>", "trial_period_days": 14, "extra_data": {}}
```

`price_id` is the internal identifier of a price (`404 Price not found`
otherwise); `trial_period_days` is 0 to `MAX_TRIAL_PERIOD_DAYS`. The local record stores the
Stripe subscription id, the id of the first subscription item (needed by
metered billing), the status returned by Stripe and the billing period.

### Cancelling and syncing

`DELETE` cancels at the end of the period by default and sets
`cancel_at_period_end`; with `immediately=true` the subscription is
cancelled at once and `canceled_at` is set. `POST .../sync` fetches the
subscription from Stripe and refreshes status, `cancel_at_period_end`, the
period dates (read from the subscription item), the item id and
`canceled_at`; a Stripe failure gives `502`.

### Upgrading with proration

Both upgrade endpoints take:

```json
{"new_price_id": "<internal price id>", "proration_behavior": "create_prorations"}
```

`proration_behavior` is `create_prorations` (default, credit applied to the
next invoice), `always_invoice` (invoice immediately) or `none`.

Validation shared by the preview and the upgrade: the subscription must be
`active` or `trialing` (`400` otherwise), the new price must exist (`404`),
belong to the same tenant (`403`) and differ from the current one (`400
Already subscribed to this plan`). Stripe errors give `502`.

- The preview answers the plan names, the current and new amounts, the
  proration line items (each with a `display_amount` helper that appends the
  currency code, e.g. `10.50 EUR`), `subtotal`, `total` (the proration only,
  not the whole next invoice), `credit_applied` and `currency` (the
  configured default when Stripe gives none).
- The upgrade answers the updated `subscription`, `proration_applied`,
  `amount_due` and the `invoice_id` when an invoice was created.

## Configuration

| Variable | Default | Purpose |
|----------|---------|---------|
| `MAX_TRIAL_PERIOD_DAYS` | `730` | Upper bound of `trial_period_days` |
| `LIST_DEFAULT_LIMIT`, `LIST_MAX_LIMIT` | `100`, `1000` | Page size of the list endpoints (introduced with the customers) |
| `DEFAULT_CURRENCY` | `usd` | Currency of proration amounts that give none |

## How it is tested

pytest (`apps/billing/tests`):

- `test_schemas_subscription.py`: `display_amount` of proration line items
  and `display_total` of the upgrade preview, the currency default and the
  trial period bound;
- `test_routes_platform_subscriptions.py`: `TestListSubscriptions`,
  `TestListCustomerSubscriptions`, `TestGetSubscriptionByExternalId`,
  `TestGetSubscription`, `TestCreateSubscription`,
  `TestUpdateSubscription`, `TestCancelSubscription`,
  `TestSyncSubscription`, `TestPreviewSubscriptionUpgrade` and
  `TestUpgradeSubscription`.

behave (`apps/billing/features/subscriptions.feature`):

- Create a subscription;
- List subscriptions for a SaaS app;
- List subscriptions for a customer;
- Get a subscription by ID;
- Get subscription by external_id;
- Update a subscription;
- Cancel a subscription at period end;
- Cancel a subscription immediately;
- Sync subscription from Stripe;
- Preview subscription upgrade;
- Upgrade subscription to new plan;
- Get non-existent subscription returns 404.
