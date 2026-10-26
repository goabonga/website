# Client status webhooks

Registering a domain starts a pipeline of minutes (DNS check, certificate,
nginx). Until now an application had to poll `GET /domains/{id}/status` or hold an
SSE stream open. With a webhook the service calls the application when something
happens: the application registers a URL and a shared secret once, and every status
change of its domains is POSTed to it as signed JSON, retried by Celery when the
receiver is down.

## Configuring a client

An administrator sets `webhook_url` and `webhook_secret` on the authorized client
(client administration page):

```bash
export CUSTOM_DOMAIN_WEBHOOK_SECRET=...   # at least 32 characters, from your secret store
custom-domain create-client --client-id my-app --name "My app" \
    --upstream app.internal:8000 --cname apps.example.com \
    --webhook-url https://my-app.example.com/hooks/custom-domain
```

or through `POST`/`PUT /api/v1/admin/clients[/{id}]`, or `clients.create(...,
webhook_url=..., webhook_secret=...)` in the SDK. Rules:

- The URL must be `https://` (and `http://` only when `WEBHOOK_ALLOW_INSECURE_URLS`
  is true, for a development setup), absolute, with no credentials.
- The secret is at least 32 characters, chosen by the operator and shared with the
  application out of band. A URL without a secret is refused (`400`).
- The secret is stored as is (it has to be, to sign) and never returned: the client
  object carries `webhook_url` and `has_webhook_secret` only. To rotate it, send a
  new `webhook_secret`; to stop the notifications send `webhook_url: null`.
- A deactivated client, or one without a webhook, receives nothing.

The columns are added by the alembic revision `003_client_webhook`.

## Events

Webhooks are derived from the progress events the tasks already publish (SSL
provisioning page). Step events (`step_started`, ...) are not sent.

| Webhook event | When | `data` |
| --- | --- | --- |
| `domain.status_changed` | Every status change | `status`, `previous_status`, `timestamp` |
| `domain.active` | Provisioning finished: the domain is served | `status`, `ssl_expires_at`, `timestamp` |
| `domain.failed` | A step failed for good | `code` (for example `DNS_VERIFICATION_FAILED`, `SSL_PROVISIONING_FAILED`, `DEPROVISIONING_FAILED`), `message`, `timestamp` |
| `domain.deleted` | Deprovisioning finished: nginx file removed, domain soft-deleted | `status`, `deleted`, `timestamp` |

`domain.status_changed` also fires for the change that `domain.active` and
`domain.failed` follow, so an application that only cares about the outcome can
subscribe to those two and ignore the rest.

## The request

`POST <webhook_url>` with `Content-Type: application/json` and a body:

```json
{
  "id": "0b4f...-delivery id, identical on every retry",
  "event": "domain.active",
  "created_at": "2026-01-01T12:00:00+00:00",
  "domain": {
    "id": "...", "domain": "shop.example.com", "status": "active",
    "client_id": "my-app", "owner_id": "org_123", "owner_type": "organization",
    "metadata": {}, "error": null
  },
  "data": {"status": "active", "ssl_expires_at": "...", "timestamp": "..."}
}
```

`domain` is a snapshot taken when the delivery is made (so it can be newer than the
event), `data` the details of the event. Headers:

| Header | Value |
| --- | --- |
| `X-Custom-Domain-Signature` | `t=<unix time>,v1=<hex>`: HMAC-SHA256 of `"<t>.<raw body>"` with the secret. |
| `X-Custom-Domain-Event` | The event name. |
| `X-Custom-Domain-Delivery` | The delivery id (also `id` in the body). |

Answer with any `2xx` within `WEBHOOK_TIMEOUT_SECONDS`. Redirects are not followed.
Anything else, a timeout or a network error is retried with an exponential
back-off starting at `WEBHOOK_RETRY_DELAY_SECONDS` and doubling, up to
`WEBHOOK_MAX_RETRIES` retries; then the delivery is given up (logged). The
delivery id and `created_at` do not change between attempts, the signature
timestamp does. Handlers must therefore be idempotent (deduplicate on `id`) and
tolerate events arriving out of order (compare `domain.status`, which is current).

## Verifying a delivery

Always verify the signature on the **raw** bytes before trusting the payload. The
SDK does it, including the replay check (a timestamp older than five minutes is
refused):

```python
from custom_domain.client import WebhookSignatureError, construct_event

def handle(request):                      # any framework: raw body + headers
    try:
        event = construct_event(
            request.body,
            request.headers["X-Custom-Domain-Signature"],
            secret=WEBHOOK_SECRET,
        )
    except WebhookSignatureError:
        return 400
    if event.event == "domain.active":
        activate(event.domain["domain"])
    return 204
```

`verify_webhook_signature(body, header, secret, tolerance_seconds=300)` only
checks and returns the timestamp; `WebhookEvent` has `id`, `event`, `created_at`,
`domain`, `data` and `status`. A header may carry several `v1=` values, so a
secret can be rotated without losing deliveries: the receiver accepts either. The
signing code is `custom_domain.webhook_signature` (standard library only) for a
receiver that is not written in Python: recompute `HMAC_SHA256(secret, t + "." + body)`
and compare in constant time.

## How it works

`publish_event` (SSL provisioning page) calls `notify_webhook`, which queues the
Celery task `deliver_webhook` on the worker queue for the events above. The task
loads the domain and its client, skips the delivery if the client is unknown,
inactive or has no webhook, builds the body and posts it. Queuing never raises: a
broker failure is logged and the provisioning goes on.

## Settings

| Variable | Default | Description |
| --- | --- | --- |
| `WEBHOOK_TIMEOUT_SECONDS` | `10` | Timeout of one delivery attempt. |
| `WEBHOOK_MAX_RETRIES` | `5` | Retries after the first attempt. |
| `WEBHOOK_RETRY_DELAY_SECONDS` | `60` | Delay before the first retry; it doubles each time. |
| `WEBHOOK_ALLOW_INSECURE_URLS` | `false` | Accept `http://` webhook URLs (development only). |

## How it is tested

- pytest: `test_webhook_signature.py` (the signature format, replay window, secret
  rotation, the SDK helpers and that the service and the SDK agree),
  `test_tasks_webhooks.py` (body, signed request, skipped deliveries, retries with
  back-off, the event mapping and the queuing from `publish_event`) and
  `test_client_webhook_config.py` (model and migration, URL and secret validation,
  the admin routes, the command line, the SDK dataclasses).
- behave: `features/webhooks.feature` configures a webhook through the admin API
  (the secret is never returned, a URL needs a secret, `http` is refused) and runs
  the real tasks in-process with Redis and the HTTP call faked: a provisioned, a
  failed and a deleted domain notify their client with correctly signed requests,
  a client without webhook or a deactivated one receives nothing, a failing receiver
  causes a retry, and the SDK verifies a delivery and rejects an altered or forged
  one.

Not verified: a delivery to a real HTTP receiver, and the behaviour of the Celery
broker when it is unreachable while an event is published.
