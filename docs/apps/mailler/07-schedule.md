# Scheduling and periodic tasks

Emails can be stored with a delivery time, and Celery beat runs the periodic
tasks that queue them when due and keep the database tidy.

## Endpoint

| Endpoint | Method | Scope | Description |
| --- | --- | --- | --- |
| `/api/v1/schedule` | POST | `mailler:send` | Store an email to be delivered at `scheduled_at` |

The body is the [send](04-send.md) request plus a required `scheduled_at`
(ISO 8601 date and time). The response has the same shape as the send
response with `status` set to `scheduled`. The email is stored as `pending`
with `scheduled_at` set and is not queued: the beat task below picks it up
when it is due. A missing or invalid `scheduled_at` gives `422`, and so does
a request without any sender (neither `from_email` nor `DEFAULT_FROM`). The
email is owned by the client of the token, like an email sent immediately.

## Periodic tasks

All tasks live in `mailler.tasks.scheduler` and are registered in the Celery
beat schedule (`mailler.celery`).

| Task | Schedule | Description |
| --- | --- | --- |
| `process_scheduled_emails` | every minute | Queue up to `SCHEDULED_EMAIL_BATCH` `pending` emails whose `scheduled_at` has passed; returns `{"queued": n}` |
| `requeue_stuck_emails` | every 2 minutes | Requeue up to `STUCK_EMAIL_BATCH` immediate (not scheduled) emails still `pending` after `STUCK_EMAIL_MINUTES` minutes (argument `stuck_minutes`); returns `{"requeued": n}` |
| `cleanup_old_emails` | daily at 03:00 UTC | Delete emails created more than `EMAIL_RETENTION_DAYS` days ago (argument `days`); returns `{"deleted": n}` |
| `aggregate_daily_stats` | daily at 00:05 UTC | Rebuild yesterday's `provider_stats` rows from the `emails` table |

Run the scheduler next to a worker:

```bash
uv run --package mailler celery -A mailler.celery:celery_app beat --loglevel=info
```

Beat only needs the broker; the tasks themselves run on the worker, which
needs database access.

## Settings

| Variable | Default | Description |
| --- | --- | --- |
| `STUCK_EMAIL_MINUTES` | `5` | Age after which a `pending` immediate email is queued again |
| `STUCK_EMAIL_BATCH` | `50` | Stuck emails queued again per run |
| `SCHEDULED_EMAIL_BATCH` | `100` | Due scheduled emails queued per run |
| `EMAIL_RETENTION_DAYS` | `90` | Age after which emails are deleted |

## How it is tested

- pytest: `tests/test_routes_schedule.py`, `tests/test_tasks_scheduler.py`,
  the beat schedule cases in `tests/test_celery_config.py`, plus routing
  cases in `tests/test_main.py`.
- behave: `features/schedule.feature`. API scenarios check that a scheduled
  email is stored and not queued, validation, authentication and scope.
  Task scenarios seed emails with relative ages and schedule times in the
  in-process SQLite database and run each periodic task directly, checking
  what gets queued, requeued, deleted and aggregated.
