# Outbound webhooks and Celery

Tenants can subscribe HTTPS endpoints to events of the platform. This
feature adds the webhook service (subscription matching, signing, SSRF
protection, dispatch), the Celery application and the tasks that deliver,
retry and clean up deliveries. The later features emit events through the
`safe_dispatch` helper added here.

## What it does

### Celery application

`auth.celery.celery_app` is the Celery application (`auth.celery:celery_app`)
used by the worker and the beat scheduler. It uses JSON serialization, a
dedicated `auth` queue (`task_default_queue = "auth"`) so that it does not
collide with the other applications sharing the broker, late acknowledgement
and a fair prefetch of 1. Tasks are discovered in `auth.tasks`. The beat
schedule currently contains the two webhook jobs; the maintenance feature
adds the others.

### Webhook service

`auth.services.webhook` provides:

- `compute_matching_patterns(event)`: the subscription patterns matching an
  event. For `mfa.challenge.failed` they are `mfa.challenge.failed`, `*`,
  `mfa.*` and `mfa.challenge.*`.
- `sign_body(secret, body, timestamp)`: the `X-Webhook-Signature` value
  `t=<unix_ts>,v1=<hmac_sha256_hex>`, where the HMAC covers
  `"<timestamp>.<body>"` so that a captured signature cannot be replayed with
  another timestamp.
- `validate_target_url(url)`: accepts `http` and `https` URLs only and, unless
  `WEBHOOK_ALLOW_PRIVATE_NETWORKS` is enabled, rejects hosts that resolve to
  private, loopback, link-local, multicast, reserved or unspecified
  addresses (SSRF protection). The check is repeated at every delivery
  attempt.
- `build_envelope` and `build_request_headers`: the JSON body
  (`id`, `event`, `tenant_id`, `created_at`, `data`) and the headers sent on
  each attempt (`X-Webhook-Id`, `X-Webhook-Event`, `X-Webhook-Delivery`,
  `X-Webhook-Attempt`, `X-Webhook-Signature`, `X-Webhook-Timestamp`, plus
  the custom headers of the webhook, which cannot override these).
- `WebhookService`: CRUD helpers for the tenant webhooks, test and replayed
  deliveries, and `dispatch`, which stores one `pending` delivery per matching
  active webhook inside the caller's transaction and queues the
  `deliver_webhook` task for each.
- `safe_dispatch`: best-effort wrapper for services and routes. It ignores a
  missing tenant and never raises, so a webhook problem cannot break the
  business action that triggered it.

`WebhookEvent` (in `auth.db.models.tenant`) lists the events: user
lifecycle (`user.*`), authentication (`login.*`, `logout`, `session.*`),
MFA (`mfa.*`), membership (`member.*`), OAuth2 clients (`client.*`),
identity providers (`idp.*`), personal access tokens (`pat.*`), roles
(`role.*`), tenant changes (`tenant.*`), security (`security.*`) and
`webhook.test`. Subscriptions accept exact names, group wildcards such as
`user.*` and `*`.

### Tasks

| Task | Beat schedule |
| --- | --- |
| `cleanup_webhook_deliveries` | `cleanup-webhook-deliveries`, cron `15 3 * * *` |
| `deliver_webhook` | on demand |
| `retry_pending_webhooks` | `retry-pending-webhooks`, cron `* * * * *` |

- `deliver_webhook(delivery_id)` performs one attempt. A 2xx answer marks the
  delivery `success` and resets the webhook failure count. Any other answer or
  transport error either schedules a retry (`retrying`, with a backoff of 1
  minute, 5 minutes, 30 minutes, 2 hours and then 12 hours) or marks the
  delivery `failed` once `max_attempts` is reached. Redirects are not
  followed and the captured response body is truncated.
- `retry_pending_webhooks` runs every minute and re-enqueues the deliveries
  whose retry time has elapsed. It flips them back to `pending` in a single
  `UPDATE`, so two overlapping ticks never enqueue the same delivery twice.
- `cleanup_webhook_deliveries` runs daily at 03:15 and deletes deliveries
  older than the retention window, then trims each webhook to its cap.

The tasks use the synchronous session helper `get_sync_db`. The SQL they
need lives in `auth.db.repositories.cleanup`.

## Endpoints

This feature adds no HTTP endpoint.

Webhooks are managed through the organisation API, a later feature.

## Settings

| Variable | Default | Description |
| --- | --- | --- |
| `CELERY_BROKER_URL` | `redis://localhost:6379/0` | Redis URL of the Celery broker |
| `CELERY_RESULT_BACKEND` | unset | Disabled by default (fire-and-forget tasks) |
| `WEBHOOK_DELIVERY_TIMEOUT_SECONDS` | `10` | HTTP timeout per attempt |
| `WEBHOOK_MAX_ATTEMPTS` | `5` | Retries before giving up |
| `WEBHOOK_RETENTION_DAYS` | `30` | Delete delivery rows older than this |
| `WEBHOOK_RETENTION_MAX_PER_HOOK` | `1000` | Cap rows per webhook |
| `WEBHOOK_RESPONSE_BODY_MAX_BYTES` | `8192` | Truncate captured response body |
| `WEBHOOK_ALLOW_PRIVATE_NETWORKS` | `False` | SSRF escape hatch (dev only) |

Run a worker with:

```bash
uv run --package auth celery -A auth.celery:celery_app worker -Q auth --loglevel=info
uv run --package auth celery -A auth.celery:celery_app beat --loglevel=info
```

`compose.yml` now also starts a local Redis on port 6384 for that purpose.

## Data model

Uses `tenant_webhooks` (URL, secret, subscribed events, custom headers, last
status and failure count) and `webhook_deliveries` (event, request and
response, attempt counters, status `pending`, `retrying`, `success` or
`failed`, `next_retry_at`).

## Tests

- pytest: 5 new test modules.
  New modules: `tests/test_celery_app.py`, `tests/test_cleanup_repository.py`, `tests/test_tasks_webhooks.py`, `tests/test_webhook_repository.py`, `tests/test_webhook_service.py`.
- behave: `features/webhooks.feature` with the scenarios *Subscriptions match exact events and wildcards*, *Deliveries are signed with a timestamped HMAC*, *Unsafe target URLs are rejected*, *A public target URL is accepted*, *An event creates a delivery for each subscribed endpoint*, *An unsafe endpoint receives no delivery*, *A successful delivery is recorded*, *A failing endpoint is retried with a backoff*, *The last failed attempt marks the delivery as failed*, *The Celery application is configured for the auth queue*.

The behave scenarios keep everything in process: the repository is an
in-memory fake, the HTTP endpoint is an `httpx.MockTransport`, and the
Celery task function is called directly without a broker.
