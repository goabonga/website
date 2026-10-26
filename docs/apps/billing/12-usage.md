# Usage

Metered prices bill what a customer consumed. Tenants report usage events
to this API; the events are stored locally as `pending` and are sent to
Stripe in batches by the background tasks feature, so reporting stays fast
and survives Stripe outages.

## Endpoints

| Path | Method | Scope | Purpose |
|------|--------|-------|---------|
| `/usage/{saas_id}/report` | POST | `billing:usage:write` | Record one usage event (`201`) |
| `/usage/{saas_id}/batch` | POST | `billing:usage:write` | Record up to `USAGE_BATCH_MAX_EVENTS` usage events (`201`) |

### Request

```json
{
  "subscription_id": "<internal subscription id>",
  "quantity": 50,
  "timestamp": "2026-01-15T10:00:00Z",
  "idempotency_key": "order-123",
  "action": "api_call",
  "metadata": {}
}
```

The batch endpoint takes `{"events": [ ...1 to `USAGE_BATCH_MAX_EVENTS`
events like above... ]}` and answers the list of events in the same order.

| Field | Rules |
|-------|-------|
| `subscription_id` | Required; the subscription must belong to the tenant (`404`) |
| `quantity` | Integer `>= 1` |
| `timestamp` | Defaults to the time of the call |
| `idempotency_key` | Up to 255 characters, unique per tenant: reporting the same key again for the same tenant returns the stored event instead of creating a new one (also inside one batch), while another tenant can use the same key freely |
| `action` | Up to 100 characters, free label |
| `metadata` | Free-form JSON, stored in `extra_data` |

A subscription without a Stripe subscription item id (not a metered
subscription) gives `400`. In a batch, one invalid event fails the whole
request.

### Response

The stored event: `id`, `subscription_id`, `quantity`, `timestamp`,
`idempotency_key`, `status` (`pending`, `reported` or `failed`),
`stripe_usage_record_id`, `reported_at`, `error_message`, `action`,
`metadata` and `created_at`. The `metadata` field is mapped from the
`extra_data` column. Each stored event also carries the `saas_app_id` of its
tenant, which the unique `(saas_app_id, idempotency_key)` constraint and the
idempotency lookups rely on.

## Configuration

| Variable | Default | Purpose |
|----------|---------|---------|
| `USAGE_BATCH_MAX_EVENTS` | `100` | Largest batch accepted by `/usage/{saas_id}/batch` |

## How it is tested

pytest (`apps/billing/tests/test_routes_usage.py`): `TestReportUsage` and
`TestReportUsageBatch` (unknown tenant or subscription, non-metered
subscription, idempotency, defaults) and `TestUsageIdempotencyScoping`
(tenant recorded on the event, idempotency lookup scoped to the tenant,
repeated key inside a batch, batch size bound) with a mocked database
session.

behave (`apps/billing/features/usage.feature`), with a metered price, a
customer and a subscription created through the API:

- Report a single usage event;
- Report batch usage events;
- Idempotency key prevents duplicates;
- The same idempotency key in a batch is recorded once;
- Two SaaS apps can use the same idempotency key;
- A subscription of another SaaS app cannot receive usage.
