# Subscription actions

Two intent-based actions complete the subscription lifecycle of the previous
page: cancel and reactivate. They are the calls a tenant makes on behalf of
a customer who ends or resumes a plan, and they sit on top of the same
Stripe logic as `DELETE` and `PATCH` on a subscription, which remain
available.

## Endpoints

Both routes live under `/platform/{saas_id}/subscriptions/{subscription_id}`
and require `billing:platform:write`. As everywhere in the platform API, a
subscription is looked up through its customer, so one that belongs to
another tenant is `404`.

| Path | Method | Purpose |
|------|--------|---------|
| `.../cancel` | POST | Cancel at the end of the paid period (default) or immediately |
| `.../reactivate` | POST | Undo a cancellation scheduled for the end of the period |

Both answer the updated subscription (same body as `GET`).

## Cancel

The body is optional:

```json
{"cancel_at_period_end": true}
```

- `cancel_at_period_end: true` (the default, also used when there is no
  body): Stripe stops renewing the subscription but keeps it running. The
  local record keeps its status (`active` or `trialing`), gets
  `cancel_at_period_end = true` and no `canceled_at`. The customer keeps
  the service they paid for; when the period ends Stripe sends
  `customer.subscription.deleted` and the webhook feature moves the record
  to `canceled` and notifies the tenant.
- `cancel_at_period_end: false`: the subscription is canceled at once.
  The status becomes `canceled` and `canceled_at` is set.
- Repeating a period-end cancellation is harmless (`200`). A subscription
  that is already `canceled` or `incomplete_expired` gives `409`.
- A Stripe error gives `502` and leaves the local record untouched.

Stripe also emits `customer.subscription.updated` for a scheduled
cancellation, so the tenant is notified through the webhook feature, not by
these routes.

## Reactivate

Clears a scheduled cancellation: the subscription keeps renewing and
`cancel_at_period_end` returns to `false`.

- Only a running subscription can be reactivated. A `canceled` or
  `incomplete_expired` subscription cannot come back, whatever Stripe says:
  the answer is `409` and the tenant has to create a new subscription
  (typically through a new Checkout session).
- Reactivating a subscription that is not scheduled for cancellation
  changes nothing and answers `200` without calling Stripe.
- A Stripe error gives `502`.

## Relationship with `DELETE` and `PATCH`

| Existing call | Equivalent action |
|---------------|-------------------|
| `DELETE .../subscriptions/{id}` | `POST .../cancel` (`immediately=true` is `cancel_at_period_end: false`) |
| `PATCH .../subscriptions/{id}` with `{"cancel_at_period_end": false}` | `POST .../reactivate` |

The actions add the explicit `409` answers for subscriptions that cannot be
canceled or reactivated; the older calls are unchanged.

## Configuration

No new variable.

## How it is tested

pytest (`apps/billing/tests/test_routes_platform_subscription_actions.py`):
`TestCancelAction` (default and explicit period-end cancellation, immediate
cancellation, already canceled, Stripe failure, unknown subscription and
tenant, authentication) and `TestReactivateAction` (scheduled cancellation,
running subscription, final statuses, Stripe failure, unknown subscription,
authentication), with a mocked database session and Stripe service.

behave (`apps/billing/features/subscription_actions.feature`), with a
Stripe mock that keeps a period-end cancellation `active`:

- Cancel at the end of the period by default;
- Cancel at the end of the period explicitly;
- Cancel immediately;
- Reactivate a subscription scheduled for cancellation;
- Reactivating a running subscription changes nothing;
- A canceled subscription cannot be reactivated;
- A canceled subscription cannot be canceled again;
- A subscription of another SaaS app is not found;
- The actions require authentication.
