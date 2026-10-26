# Background tasks

A Celery worker and a beat scheduler run the work that should not block web
requests: sending emails and executing the workspace deletion life cycle. The
Celery application is `knowledge.celery:celery_app` and the task module is
`knowledge.tasks`.

## Celery application

- Broker `CELERY_BROKER_URL`, result backend `CELERY_RESULT_BACKEND`.
- Dedicated queue and exchange named by `CELERY_QUEUE` (`knowledge` by
  default), which is also the default queue: workers must be started with
  `-Q "$CELERY_QUEUE"`.
- JSON serialization only, the timezone of `CELERY_TIMEZONE` (`UTC` by default)
  with UTC enabled, tasks tracked as started, a hard time limit of
  `CELERY_TASK_TIME_LIMIT` seconds (300 by default).
- Reliable delivery: late acknowledgement, rejection when the worker is lost,
  prefetch multiplier of 1, broker connection retried on startup.

Task names are `knowledge.tasks.<function>`. They were `app.tasks.<function>`
before the code moved into the `knowledge` package, so the queue should be
drained before a worker running the new code replaces one running the old
code.

## Email tasks

`send_email_task(to, template_slug, variables)` is the generic task: it sends the
template of the application with the given variables through the mailler service
(`MaillerClient.send_template`, described in [Email delivery](10-email.md)). The
templates are rendered, and the sender and the provider chosen, by mailler; the
worker needs no SMTP setting, no MJML compiler and no template file at run time.

- **Idempotency.** The id of the Celery task is the `Idempotency-Key` of the request, so
  when mailler accepted the email but the answer was lost, the retry of the task does not
  send a second one. A new task (a new invitation) has a new key.
- **Retries.** A failure that can pass (mailler or the OAuth2 server unreachable, `5xx`,
  `429` rate limit or quota) retries the task up to `MAILLER_MAX_RETRIES` times (3 by
  default) with a delay of `MAILLER_RETRY_DELAY` seconds doubled each time (60 s, 120 s,
  240 s). A failure that will not pass (`403` client not registered or deactivated, `404`
  template not imported, `422` template not active or not renderable, missing
  configuration) is not retried.
- **Result.** The task never raises once the retries are over: it returns
  `{"success": true, "email_id": "...", "missing_variables": [...]}` or
  `{"success": false, "error": "...", "status_code": ...}`.

Typed wrappers prepare the variables of each template; the subject belongs to the template
(its `subject_template`), not to the task:

| Task | Template | Variables |
| --- | --- | --- |
| `send_workspace_deletion_email` | `workspace_deletion` | `workspace_name`, `confirmation_url`, `user_email`, `year` |
| `send_workspace_deletion_scheduled_email` | `workspace_deletion_scheduled` | `workspace_name`, `deletion_date`, `user_email`, `year` |
| `send_workspace_deleted_email` | `workspace_deleted` | `workspace_name`, `support_url`, `user_email`, `year` |
| `send_workspace_deletion_reminder_email` | `workspace_deletion_reminder` | `workspace_name`, `deletion_date`, `cancel_url`, `user_email`, `year` |
| `send_workspace_invitation_email` | `workspace_invitation` | `workspace_name`, `inviter_name`, `role`, `invitation_url`, `user_email`, `year` |

## Workspace deletion tasks

A workspace deletion goes through the `workspace_deletion_requests` table (see
the [data model](01-data-model.md)): a request is confirmed, scheduled for the
end of the billing period and finally executed.

- `process_scheduled_deletions` finds the `scheduled` requests whose
  `scheduled_deletion_at` has passed, deletes the organization (its
  collections, documents, members and invitations go with it through the
  cascades) and marks the request as confirmed. Each request is handled in its
  own transaction, so one failure does not block the others. It returns
  `{"deleted": n, "errors": m}`.
- `send_deletion_reminders` looks at the `scheduled` requests without
  reminder; when the deletion is less than a day away it queues the reminder
  email with a cancellation link
  `<APP_BASE_URL>/organizations/delete/cancel/<cancel token>` and records the
  reminder date. It returns `{"sent": n, "errors": m}`.

Both run from the beat schedule (`process-scheduled-deletions` and
`send-deletion-reminders`) every `DELETION_CHECK_INTERVAL` seconds (hourly by default). Each creates its own async SQLAlchemy engine from
`DATABASE_URL` and runs it to completion in a private event loop.

## Running

From the root of the workspace, with Redis and PostgreSQL available (see
`compose.yml`):

```bash
uv run --package knowledge celery -A knowledge.celery:celery_app worker -Q "$CELERY_QUEUE"
uv run --package knowledge celery -A knowledge.celery:celery_app beat
```

## Settings

| Variable | Default | Description |
| --- | --- | --- |
| `CELERY_BROKER_URL` | `redis://localhost:6387/0` | Broker. |
| `CELERY_RESULT_BACKEND` | `redis://localhost:6387/1` | Result backend. |
| `CELERY_QUEUE` | `knowledge` | Queue (and exchange) the application publishes to; the worker must consume it. |
| `CELERY_TIMEZONE` | `UTC` | Timezone of the Celery application. |
| `CELERY_TASK_TIME_LIMIT` | `300` | Seconds a task may run before it is killed. |
| `DELETION_CHECK_INTERVAL` | `3600.0` | Seconds between two passes of the deletion and reminder tasks. |
| `APP_BASE_URL` | empty | Public base URL used in the links of the emails. |

The mailler settings (`MAILLER_MAX_RETRIES`, `MAILLER_RETRY_DELAY`, ...) are on the
[Email delivery](10-email.md) page, the database settings are those of the previous features.

## Tests

pytest:

- `unit/test_tasks.py`: the send helper (idempotency key shared by the retries of a task,
  retry with growing delays, end of the retries, failures that are not retried), the
  variables of every typed wrapper against the shipped templates, and the two periodic
  tasks (success, per-item errors, missing organizations).
- `unit/test_celery_config.py`: queue, timezone and time limit from the settings,
  serialization, delivery settings, task registration and beat schedule.

behave (`features/background_tasks.feature`): tasks are called in-process with the
mailler service of the email feature (a mocked transport) and a fake database session.

- The worker listens on its own queue
- Periodic tasks are scheduled hourly
- An email task sends the template through mailler
- The deletion confirmation email carries the confirmation link
- An email whose template is not imported is reported without retry
- An email is retried when mailler is down
- Scheduled deletions that are due are executed
- A reminder is sent the day before the deletion
- No reminder is sent too early
