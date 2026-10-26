# Prices

A price says how much a product costs and how it is billed. Like products,
prices are created in Stripe first and then stored locally with the real
Stripe identifier.

## Endpoints

All routes live under `/platform/{saas_id}/products/{product_id}/prices`.
An unknown SaaS application or a product that does not belong to it gives
`404`.

| Path | Method | Scope | Purpose |
|------|--------|-------|---------|
| `.../prices` | POST | `billing:platform:write` | Create a price (`201`) |
| `.../prices` | GET | `billing:platform:read` | List the prices of a product |
| `.../prices/{price_id}` | GET | `billing:platform:read` | Read one price |
| `.../prices/{price_id}` | PATCH | `billing:platform:write` | Rename or deactivate a price |

### Request

```json
{
  "nickname": "Monthly",
  "currency": "usd",
  "unit_amount": 2900,
  "billing_type": "recurring",
  "recurring_interval": "month",
  "recurring_interval_count": 1,
  "usage_type": "licensed"
}
```

| Field | Rules |
|-------|-------|
| `currency` | Exactly 3 characters, default `DEFAULT_CURRENCY` |
| `unit_amount` | Integer in cents, `>= 0`; `null` is allowed (metered or custom pricing) |
| `billing_type` | `recurring` (default) or `one_time` |
| `recurring_interval` | `day`, `week`, `month` or `year`; a recurring price without interval gets `DEFAULT_RECURRING_INTERVAL`, and the same value is sent to Stripe and stored locally |
| `recurring_interval_count` | 1 to 365, default 1 |
| `usage_type` | `licensed` (default) or `metered`; metered prices aggregate usage with `sum` and carry no amount in Stripe |

Stripe prices are mostly immutable, so `PATCH` only accepts `nickname` and
`is_active` (sent to Stripe as `active`). The list hides inactive prices
unless `include_inactive=true`.

### Synchronizing a catalog

The `POST /platform/saas/{saas_id}/sync-stripe` endpoint of the SaaS
application feature now has something to do: products and prices whose
identifiers are not real Stripe identifiers (rows created outside the API,
for example by a provisioning script) are created on Stripe and updated with
the real identifiers. Nothing in the application seeds such rows: the
catalog of a tenant is created through the API.

## Configuration

| Variable | Default | Purpose |
|----------|---------|---------|
| `DEFAULT_CURRENCY` | `usd` | Currency of a price that gives none (introduced with the data model) |
| `DEFAULT_RECURRING_INTERVAL` | `month` | Interval of a recurring price that gives none (introduced with the Stripe service) |

## How it is tested

pytest (`apps/billing/tests`):

- `test_schemas_price.py`: validation of `PriceCreate` (intervals, amounts,
  currency length and configured default, interval count bounds, one-time
  prices, defaults);
- `test_routes_platform_prices.py`: `TestGetProductOr404`,
  `TestCreatePrice`, `TestListPrices`, `TestGetPrice` and
  `TestUpdatePrice` with a mocked database session and Stripe service,
  including the configured currency and interval defaults.

behave (`apps/billing/features/prices.feature`):

- Create a price;
- A price without currency and interval takes the configured defaults;
- List prices for a product;
- Get a price by ID;
- Update a price nickname;
- Deactivate a price;
- Get non-existent price returns 404;
- Sync products and prices to Stripe (through the SaaS application
  endpoint).
