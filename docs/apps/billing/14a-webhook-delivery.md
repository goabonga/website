# Notification delivery

The notifications of the webhooks page are not sent from the request that
handles the Stripe event: they are queued on Celery and delivered by a task
that retries the failures that can succeed later. A tenant that is down for
a few minutes still receives its events, in the same form, and an event can
be told apart from a replay by its `id`.

## How a notification travels

1. A Stripe handler calls `notify_subscription_*`, which builds the event
   (envelope, data, stable `id`) and turns it into plain JSON: datetimes become
   strings, so that every attempt sends exactly the same body.
2. `dispatch_webhook` queues `billing.tasks.webhook_tasks.deliver_saas_webhook`
   on the queue `CELERY_QUEUE` with the identifier of the SaaS application and
   the event. Tenants without `webhook_url` are skipped before anything is
   queued. The queue holds the event, never the `webhook_secret`.
3. The worker loads the SaaS application at delivery time, so a URL or a
   secret changed after the event was queued is honored, then posts the event
   signed with `X-Billing-Signature` (HMAC-SHA256 of the raw body, unchanged).
4. If the broker is unavailable, the event is delivered at once from the
   API process, once, instead of being lost; Stripe is never made to wait for
   a broker that is down (publishing is not retried).

`notify_subscription_*` and `dispatch_webhook` now answer `True` when the
event was queued (or delivered by the fallback), not when the tenant
acknowledged it.

## Retries

A failed attempt is classified by `WebhookDeliveryError.retryable`:

| Failure | Retried |
|---------|---------|
| Network error, timeout | yes |
| `5xx`, `408`, `425`, `429` | yes |
| Any other `4xx` (the receiver refuses the event) | no |
| SaaS application deleted or without URL | no |

The task makes at most `SAAS_WEBHOOK_MAX_ATTEMPTS` attempts in total (`1`
disables the retries). The delay before the next attempt is
`SAAS_WEBHOOK_BACKOFF_SECONDS`, multiplied by `SAAS_WEBHOOK_BACKOFF_FACTOR`
after each failure and never longer than `SAAS_WEBHOOK_BACKOFF_MAX_SECONDS`;
with the defaults: 30 s, 60 s, 2 min, 4 min between the five attempts.
Whatever the attempt, the body, the event `id` and therefore the signature
are identical: a receiver that stores the identifiers it has processed gets
exactly-once behavior out of an at-least-once delivery.

When the attempts are used up the task logs an error and ends with
`{"event_id": ..., "delivered": false, "attempts": n}`; nothing else is done
with the event.

The task needs a worker on the queue `CELERY_QUEUE` (the worker of the
background tasks page) and uses `DATABASE_URL` to read the application.

## Configuration

| Variable | Default | Purpose |
|----------|---------|---------|
| `SAAS_WEBHOOK_MAX_ATTEMPTS` | `5` | Attempts in total, the first one included; `1` disables the retries |
| `SAAS_WEBHOOK_BACKOFF_SECONDS` | `30.0` | Delay before the second attempt |
| `SAAS_WEBHOOK_BACKOFF_FACTOR` | `2.0` | Multiplier applied to the delay after each failure |
| `SAAS_WEBHOOK_BACKOFF_MAX_SECONDS` | `3600.0` | Longest delay between two attempts |

`SAAS_WEBHOOK_TIMEOUT` (webhooks page) is the timeout of one attempt and
`CELERY_QUEUE` (background tasks page) the queue.

## How it is tested

pytest (`apps/billing/tests`):

- `test_services_saas_webhook.py`: `TestDispatchWebhook` (event queued with
  its identifier, JSON-serializable, same id for a replayed Stripe event,
  fallback when the broker is down), `TestDeliverEvent`, `TestNotifySubscription`;
- `test_webhook_tasks.py`: `TestRetryDelay`, `TestShouldRetry`, `TestDeliver`
  and `TestDeliverSaasWebhookTask`, run eagerly: first-attempt delivery,
  final failure, retry until success, giving up after the configured number
  of attempts, same event on every attempt, countdown given to Celery.

behave (`apps/billing/features/webhook_delivery.feature`), with Celery in
eager mode (a retry runs again at once) and a recording receiver:

- A notification is delivered at the first attempt;
- A server error is retried until the receiver accepts the event;
- Throttling is retried;
- A refusal of the receiver is final;
- The delivery gives up after the configured number of attempts;
- A single attempt disables the retries;
- The notification is sent at once when the broker is unavailable.

Delivery has been exercised against a mocked receiver and Celery's eager
mode only: it has not been run against a real Redis broker and worker.
