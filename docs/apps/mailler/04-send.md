# Sending emails

`POST /api/v1/send` stores an email and queues it on a Celery worker, which
delivers it through the chosen provider and records the outcome. This
feature introduces the Celery application, the first database tables and the
first migration.

## Endpoint

| Endpoint | Method | Scope | Description |
| --- | --- | --- | --- |
| `/api/v1/send` | POST | `mailler:send` | Store an email and queue its delivery |

Request body (`SendEmailRequest`):

| Field | Required | Description |
| --- | --- | --- |
| `to_email` | yes | Recipient address (validated) |
| `to_name` | no | Recipient name |
| `subject` | yes* | 1 to 500 characters |
| `html_content` | yes* | HTML body |
| `text_content` | no | Plain text body |
| `template_slug`, `variables` | * | Instead of the three content fields, the slug of a template of the client and its variables: see [sending from a template](18-template-sending.md) |
| `provider` | no | `brevo`, `sendgrid`, `ses` or `protonmail`, among those the client may use; defaults to the provider of its record |
| `from_email`, `from_name` | no | Sender; must be one of the identities of the client record and default to its default identity. Administrators without a record fall back to `DEFAULT_FROM` and `DEFAULT_FROM_NAME`; when no address can be determined the request is refused with `422` |
| `reply_to` | no | Reply-to address; fixed by the record when it has one |
| `metadata` | no | Free-form JSON stored with the email |

\* Either `subject` and `html_content`, or `template_slug`.

The response is `{"id", "status": "queued", "message", "task_id", "missing_variables"}`. The email
row is created with status `pending`; for machine clients (client
credentials) `user_id` is left empty and the OAuth client id (see
[client identity](02-authentication.md)) is recorded as the owner of the email.
The sender and the provider are forced or validated from the
[client registry](15-authorized-clients.md) (`403` when a requested value is
not allowed). A provider that is allowed but not configured makes the email
fail in the worker.

## Delivery task

`mailler.tasks.send.send_email_task(email_id)` runs on the queue named by
`CELERY_QUEUE` (`mailler` by default).

1. The email is loaded; unknown ids return `{"error": "Email not found"}`, and
   an email that is neither `pending` nor `queued` is left alone.
2. The email becomes `queued` (with `queued_at` and the Celery `task_id`) and
   the provider is asked to send it.
3. On success the status becomes `sent` (with `sent_at` and
   `provider_message_id`) and the provider counter is incremented.
4. On failure `retry_count` is incremented and the task is retried with an
   exponential backoff (`SEND_RETRY_DELAY` base, capped at
   `SEND_RETRY_BACKOFF_MAX`, with jitter, at most `SEND_MAX_RETRIES` Celery
   retries). When `retry_count` reaches `SEND_MAX_RETRIES` the email
   becomes `failed` (with `failed_at` and `error_message`).
5. If the provider is unknown or not configured the email fails immediately.

Daily per-provider counters (`sent`, `delivered`, `bounced`, `failed`) are
kept in the `provider_stats` table.

## Celery application

`mailler.celery:celery_app` uses the broker and result backend below, JSON
serialization, UTC, a single queue (`CELERY_QUEUE`), late acknowledgement, a prefetch
of one and a task time limit of 300 seconds (soft limit 270 seconds). Tasks
are discovered in `mailler.tasks`.

```bash
uv run --package mailler celery -A mailler.celery:celery_app worker -Q "$CELERY_QUEUE" --loglevel=info
```

## Data model and migration

Alembic revision `001` (`apps/mailler/alembic`) creates two tables:

- `emails`: recipient, sender, content, provider, `provider_message_id`,
  `status` (`pending`, `queued`, `sent`, `delivered`, `bounced`, `failed`),
  `error_message`, `retry_count`, `scheduled_at`, the lifecycle timestamps,
  `metadata` (JSONB), `client_id`, `user_id` and `task_id`.
- `provider_stats`: one row per day and provider with the four counters.

```bash
uv run --package mailler alembic -c apps/mailler/alembic.ini upgrade head
```

The migration reads `DATABASE_URL` from the application settings.

## Settings

| Variable | Default | Description |
| --- | --- | --- |
| `CELERY_BROKER_URL` | `redis://localhost:6379/0` | Celery broker |
| `CELERY_RESULT_BACKEND` | `redis://localhost:6379/1` | Celery result backend |
| `CELERY_QUEUE` | `mailler` | Queue declared by the application; workers must consume it (`-Q`) |
| `SEND_MAX_RETRIES` | `3` | Delivery attempts before an email is marked `failed` |
| `SEND_RETRY_DELAY` | `60` | Seconds before the first retry |
| `SEND_RETRY_BACKOFF_MAX` | `300` | Upper bound of the exponential retry backoff, in seconds |

## Dependencies

`celery[redis]`, `alembic` and `email-validator` (address validation of the
request schema).

## How it is tested

- pytest: `tests/test_routes_send.py`, `tests/test_tasks_send.py`,
  `tests/test_celery_config.py`, `tests/test_models_email.py`, plus
  settings and routing cases in `tests/test_config.py` and
  `tests/test_main.py`.
- behave: `features/send.feature`. Scenarios post to the API against a
  temporary SQLite database, check the stored rows and the recorded
  `delay` calls, then run the task directly with a fake provider
  (success, repeated failure, unconfigured provider, idempotence). No broker
  or PostgreSQL is needed; the PostgreSQL-specific column types are mapped to
  portable ones for the test database only.
