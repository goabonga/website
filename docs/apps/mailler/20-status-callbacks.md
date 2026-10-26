# Status callbacks

Instead of polling `GET /emails/{id}`, an application can register a callback
URL: the service posts a signed JSON notification there each time one of its
emails is sent, delivered, bounced or fails.

## Registering a callback

The callback is part of the [client record](15-authorized-clients.md), set by
an administrator through the registry API or the [command line](17-command-line.md):

| Field | Meaning |
| --- | --- |
| `callback_url` | Absolute `https` URL of the application endpoint (`http` only when `CALLBACK_ALLOW_HTTP` is set), without credentials |
| `callback_secret` | Secret that signs the notifications, at least 16 characters |

The URL and the secret go together: giving only one of them is refused with
`422`. The secret is write-only: the API and `mailler clients show` only
report `has_callback_secret`. The command line reads it from a file
(`--callback-secret-file`), so it does not appear in the process list. Both
are removed by setting them to `null` (API) or to an empty value (command
line). The URLs are provided by the operators, not by the clients.

## What is sent

A notification is queued, on the Celery worker, when an email of a client
that has a callback reaches one of the statuses `sent`, `delivered`,
`bounced` or `failed`: when the delivery task sends it or gives up on it, and
when the provider reports a delivery, a bounce or a complaint (see
[Brevo webhooks](13-webhooks.md)). The statuses `pending` and `queued` are not
notified, and neither is a failed attempt that will be retried. A notification
that cannot be queued is logged and never disturbs the delivery it reports.

The body is a compact JSON object:

```json
{
  "event": "email.status",
  "email_id": "6f1b53a8-1c83-4d44-9d7e-7f7b8a1d2c33",
  "client_id": "my-application",
  "status": "sent",
  "to_email": "newcomer@example.com",
  "provider": "brevo",
  "provider_message_id": "<202610260930.1@smtp-relay>",
  "error_message": null,
  "metadata": {"invitation": 42, "template_slug": "workspace_invitation"},
  "occurred_at": "2026-10-26T09:30:02.114250+00:00"
}
```

`metadata` is the one the application passed when it sent the email, which
lets it find the object the email was about without a lookup.

## Verifying the signature

Every request carries:

| Header | Content |
| --- | --- |
| `X-Mailler-Event` | `email.status` |
| `X-Mailler-Timestamp` | Unix time of the delivery attempt |
| `X-Mailler-Signature` | `sha256=` followed by the hexadecimal HMAC-SHA256, keyed with the secret, of `<timestamp>.<raw body>` |

The application recomputes the HMAC over the timestamp, a dot and the raw
request body, compares it in constant time, and should reject requests whose
timestamp is too old.

```python
import hashlib, hmac

def verify(secret: str, timestamp: str, body: bytes, signature: str) -> bool:
    digest = hmac.new(secret.encode(), timestamp.encode() + b"." + body, hashlib.sha256)
    return hmac.compare_digest(f"sha256={digest.hexdigest()}", signature)
```

## Delivery and retries

- Any `2xx` answer is a success. Any other answer, a timeout or a network
  error makes the worker deliver the notification again with an exponential
  backoff (`CALLBACK_RETRY_DELAY` seconds, doubling, at most one hour), up to
  `CALLBACK_MAX_RETRIES` times; after that the failure stays in the worker log
  and the notification is dropped. Applications should therefore treat the
  endpoint as idempotent and may still read the status with
  `GET /emails/{id}`.
- Notifications can arrive out of order when one of them is delivered again:
  `occurred_at` tells which is the most recent.
- A callback is sent as long as the client has one, whether the client is
  active or not.

## Settings

| Variable | Default | Description |
| --- | --- | --- |
| `CALLBACK_ALLOW_HTTP` | `false` | Accept plain `http` callback URLs |
| `CALLBACK_TIMEOUT` | `10` | Seconds to wait for the endpoint of the client |
| `CALLBACK_MAX_RETRIES` | `5` | Redeliveries of a refused notification |
| `CALLBACK_RETRY_DELAY` | `30` | Seconds before the first redelivery |

## Data model and migration

Alembic revision `009` adds the nullable `callback_url` and `callback_secret`
columns to `authorized_clients`; existing clients have no callback. The secret
is stored as it is, because it is needed to sign; protect the database like
the other secrets.

## How it is tested

- pytest: `tests/test_services_callbacks.py` (signature, payload, which
  statuses and clients are notified, errors never propagating),
  `tests/test_tasks_callbacks.py` (the signed request, refusals and network
  errors, incomplete callbacks), the notification cases of
  `tests/test_tasks_send.py` and `tests/test_routes_webhooks.py`, the
  callback cases of `tests/test_routes_clients.py` and `tests/test_cli.py`,
  `tests/test_models_client.py` and `tests/test_migration_client_callbacks.py`
  (the `009` migration on SQLite).
- behave: `features/status_callbacks.feature` (registration and validation, a
  notification on success and on a final failure with its signature and
  payload, clients without a callback, a refused notification). The endpoint
  of the client is a recorder, nothing goes on the network; the migration was
  not run on PostgreSQL.
