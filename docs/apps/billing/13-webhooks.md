# Webhooks

Two kinds of webhooks meet in the billing service:

- **Inbound**: Stripe events, received directly or through the `webhooks`
  application of the platform, keep the local database in step with Stripe.
- **Outbound**: subscription changes are pushed to the webhook URL of the
  SaaS application the subscription belongs to.

## Inbound endpoint

| Path | Method | Authentication | Purpose |
|------|--------|----------------|---------|
| `/webhooks/stripe` | POST | Stripe signature | Process a Stripe event |

**The signature is the authentication.** Stripe cannot send an OAuth token,
so the endpoint does not ask for one: billing verifies the `Stripe-Signature`
header against the raw body with `STRIPE_WEBHOOK_SECRET`
(`stripe.Webhook.construct_event`), and nothing else is needed. An event
without a valid signature is rejected before anything is read. A bearer token
that accompanies the request (the `webhooks` proxy application forwards one)
is accepted and ignored.

A deployment that wants a token on top of the signature, for instance
because the endpoint is reachable by other callers than Stripe and the
proxy, sets `STRIPE_WEBHOOK_REQUIRED_SCOPE` (for example `billing:webhooks`):
the request then needs a valid token carrying that scope (`401` without
token, `403` without the scope) and the signature check still applies.

How it is deployed: Stripe posts to the public `webhooks` gateway, which
forwards the raw payload and the `Stripe-Signature` header to this endpoint
over the Unix socket of billing (`STRIPE_INTERNAL_API_SOCKET` on the gateway).
Only the processes allowed to open that socket and the VPN clients of the
internal host name can reach the endpoint, and each of them still has to
present a payload signed with the Stripe secret.

| Situation | Answer |
|-----------|--------|
| `STRIPE_WEBHOOK_SECRET` not configured | `500 Webhook secret not configured` |
| Invalid signature or payload | `400` |
| `STRIPE_WEBHOOK_REQUIRED_SCOPE` set, no or wrong token | `401` / `403` |
| Handler failure | `500 Failed to process webhook` (the transaction is rolled back) |
| Success or unhandled event type | `200` |

Events are handled in their own database session, committed once per event.

| Event | Effect |
|-------|--------|
| `checkout.session.completed` | Create the local subscription (status `active`) for the Stripe customer when the session carries `metadata.saas_id` and a subscription; the session id is kept in the `extra_data` of the subscription (`checkout_session_id`). A session whose `saas_id` is not the tenant of the customer is ignored; one-time payments are only logged; an existing subscription is left alone. Notifies the tenant (`subscription.created`) |
| `invoice.paid` | Reactivate a `past_due` or `unpaid` subscription and notify the tenant (`subscription.updated`) |
| `invoice.payment_failed` | Mark the subscription `past_due` and notify the tenant (`subscription.updated`) |
| `customer.subscription.updated` | Copy status, period (from the subscription, or from its first item with recent Stripe API versions), cancellation flags from Stripe and notify the tenant (`subscription.updated`) |
| `customer.subscription.deleted` | Mark the subscription `canceled` and notify the tenant (`subscription.deleted`) |
| `customer.created` | Create the customer when `metadata.saas_id` (an existing SaaS application) and `metadata.external_id` are present; restore a soft-deleted customer |
| `customer.updated` | Copy email and name |
| `customer.deleted` | Soft delete the customer (`deleted_at`) |

## Outbound notifications

`billing.services.saas_webhook` posts JSON to `SaasApp.webhook_url`:

```json
{
  "id": "6f1c3a3e-8e0a-5f55-9a53-0c3e1d2b7a10",
  "type": "subscription.updated",
  "created": "2026-01-15T10:00:00+00:00",
  "saas_id": "<internal tenant id>",
  "saas_slug": "example-app",
  "data": {
    "subscription_id": "...",
    "customer_external_id": "user-42",
    "status": "active",
    "plan_name": "Pro",
    "plan_slug": "pro",
    "price_id": "<internal price id>",
    "limits": {"max_seats": 10, "emails_per_day": -1},
    "current_period_start": "...",
    "current_period_end": "...",
    "cancel_at_period_end": false,
    "canceled_at": null
  }
}
```

- `subscription.created`, `subscription.updated` and `subscription.deleted`
  carry the same `data`.
- `id` identifies the event and is **stable**: it is derived from the
  tenant, the Stripe event that caused the notification, the notification
  type and the subscription. When Stripe delivers the same event again, the
  tenant receives the same `id` and can ignore what it already processed.
- `saas_slug` and `saas_id` name the tenant. `plan_slug` is the identifier of
  the plan inside the tenant (what a receiver should map on: `plan_name` is
  a display name that can be renamed), `price_id` the internal price and
  `limits` the quota limits of the plan, free-form integers with the names the
  tenant chose, or `null` when the plan declares none.
- When the application has a `webhook_secret`, the body is signed with
  HMAC-SHA256 and the hex digest is sent in the `X-Billing-Signature`
  header. Receivers must compute the same HMAC over the raw body.
- The request timeout is `SAAS_WEBHOOK_TIMEOUT`. A failure (HTTP error,
  network error) is logged and never fails the Stripe event. The
  notifications are queued and retried by a Celery task, see the
  notification delivery page. Applications without a webhook URL are skipped.
- A delivery failure is classified: network errors, timeouts, `5xx`, `408`,
  `425` and `429` are retryable, any other refusal of the receiver is not.

## Configuration

| Variable | Default | Purpose |
|----------|---------|---------|
| `STRIPE_WEBHOOK_SECRET` | empty | Signing secret checked on every inbound event (introduced with the Stripe service, secret) |
| `STRIPE_WEBHOOK_REQUIRED_SCOPE` | empty | Scope a bearer token must carry on top of the signature; empty means the signature is the only authentication |
| `SAAS_WEBHOOK_TIMEOUT` | `30.0` | Timeout of a notification to a SaaS application, seconds |

## How it is tested

pytest (`apps/billing/tests`):

- `test_routes_webhooks.py`: `TestHelperFunctions`,
  `TestHandleCustomerCreated`, `TestHandleCustomerDeleted`,
  `TestHandleCustomerUpdated`, `TestHandleCheckoutSessionCompleted`,
  `TestHandleInvoicePaid`, `TestHandleInvoicePaymentFailed`,
  `TestHandleSubscriptionUpdated`, `TestHandleSubscriptionDeleted`,
  `TestWebhookHardening` (session id in `extra_data`, session of another
  tenant, event id forwarded, unknown tenant, period read from the item),
  `TestStripeWebhookRoute` (signature handling, dispatch, error cases) and
  `TestStripeWebhookAuthentication` (no token needed, proxy token ignored,
  required scope);
- `test_services_saas_webhook.py`: `TestSignPayload`, `TestGetHttpClient`,
  `TestGetSaasAppById`, `TestEventId`, `TestBuildEvent`,
  `TestBuildSubscriptionData`, `TestDeliverEvent` (success, signature,
  retryable and non-retryable failures), `TestDispatchWebhook` and
  `TestNotifySubscription` for the three notifications.
- `conftest.py` gains the `webhook_user` and `webhook_client` fixtures.

behave (`apps/billing/features/webhooks.feature`), with the Stripe signature
verification patched, events posted without token like Stripe does and the
HTTP client of the notifications replaced by a recorder:

- Customer created webhook;
- Customer deleted webhook;
- Checkout session completed webhook creates subscription;
- Invoice paid webhook;
- Subscription updated webhook;
- Invalid webhook signature returns 400;
- A webhook without bearer token is processed when it is signed;
- A webhook sent through the proxy with its token is processed;
- The signature is still required when a token is sent;
- A bearer token is required when the deployment asks for one;
- A bearer token with the required scope is accepted;
- A completed checkout stores its session on the subscription;
- A checkout session of another SaaS app is ignored;
- A customer created for an unknown SaaS app is ignored;
- The SaaS app is notified with its slug, plan slug, price, limits and an
  event id;
- A Stripe event delivered twice produces notifications with the same
  identifier.
