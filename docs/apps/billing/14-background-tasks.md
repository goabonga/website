# Background tasks

Celery runs the work that must not block API requests: reporting metered
usage to Stripe, purging old usage events and pushing catalog records that
have no real Stripe identifier to Stripe.

## Celery application

`billing.celery:celery_app` is configured as follows:

- broker `CELERY_BROKER_URL`, result backend `CELERY_RESULT_BACKEND`;
- JSON serialization only, late acknowledgements, one message prefetched
  per worker, tasks rejected when the worker is lost, task time limit
  `CELERY_TASK_TIME_LIMIT`, started state tracked;
- the single queue `CELERY_QUEUE` (exchange and routing key of the same
  name) is the default queue: start the worker on that queue;
- timezone `CELERY_TIMEZONE` (UTC enabled);
- the logging of the worker is replaced by the dual-stream configuration of
  `billing.logging.setup_logging`, at the level of `LOG_LEVEL`.

```bash
uv run --package billing celery -A billing.celery worker --loglevel=info
uv run --package billing celery -A billing.celery beat --loglevel=info
```

Only one beat process must run at a time.

## Tasks and schedule

| Task | Schedule | Purpose |
|------|----------|---------|
| `billing.tasks.usage_tasks.report_pending_usage` | every `USAGE_REPORT_INTERVAL` seconds (`batch_size=USAGE_REPORT_BATCH_SIZE`) | Send pending usage events to Stripe |
| `billing.tasks.usage_tasks.cleanup_old_usage_events` | every `USAGE_CLEANUP_INTERVAL` seconds (`days_old=USAGE_RETENTION_DAYS`) | Delete reported usage events older than the limit |
| `billing.tasks.stripe_sync_tasks.sync_all_products_to_stripe` | every `STRIPE_SYNC_INTERVAL` seconds | Create products and prices without a real Stripe id on Stripe |

The schedule entries are named `report-pending-usage`,
`cleanup-old-usage-events` and `sync-products-to-stripe`.

### report_pending_usage

Reads up to `batch_size` `pending` usage events, oldest first, and for each
one calls `StripeService.report_usage` with the subscription item id of its
subscription, the quantity, the timestamp and the idempotency key. Idempotency
keys are unique per SaaS application in the database but global in Stripe, so
the key sent to Stripe is the SHA-256 digest of the application id and of the
key given by the application: two applications can use the same key. The
event becomes `reported` (with the Stripe record id and `reported_at`) or
`failed` with an `error_message` when the subscription is missing, has no
subscription item id or Stripe rejects the call. The task returns
`{"processed": n, "success": n, "failed": n}`.

### cleanup_old_usage_events

Deletes `reported` events whose `reported_at` is older than `days_old`
days (`USAGE_RETENTION_DAYS` when the task is called without argument) and
returns `{"deleted": n}`. Pending and failed events are kept.

### sync_all_products_to_stripe

Same logic as the `sync-stripe` endpoint, for every active SaaS
application: products and prices whose Stripe id is not a real one (not
`prod_` / `price_` followed by at least 14 alphanumeric characters, as for
rows created by a provisioning script) are created on Stripe and updated with
the real identifiers; prices without amount are skipped; Stripe errors are
collected. Products created through the API already have real identifiers, so
the task normally has nothing to do. It returns the counters
`products_synced`, `prices_synced`, `products_skipped`, `prices_skipped`
and `errors`.

Task names changed with the package rename of the original project
(`app.tasks...` became `billing.tasks...`): drain the queue before deploying
a release that crosses the rename.

## Configuration

| Variable | Default | Purpose |
|----------|---------|---------|
| `CELERY_BROKER_URL` | `redis://localhost:6379/10` | Celery broker |
| `CELERY_RESULT_BACKEND` | `redis://localhost:6379/11` | Celery result backend |
| `CELERY_QUEUE` | `billing` | Queue (and exchange, routing key) of the tasks |
| `CELERY_TIMEZONE` | `UTC` | Time zone of the schedule |
| `CELERY_TASK_TIME_LIMIT` | `3600` | Hard time limit of a task, seconds |
| `USAGE_REPORT_INTERVAL` | `300.0` | Seconds between two usage reports |
| `USAGE_REPORT_BATCH_SIZE` | `100` | Usage events sent to Stripe per run |
| `USAGE_CLEANUP_INTERVAL` | `86400.0` | Seconds between two cleanups |
| `USAGE_RETENTION_DAYS` | `90` | Age after which reported usage events are deleted |
| `STRIPE_SYNC_INTERVAL` | `3600.0` | Seconds between two catalog syncs |

The tasks also use `DATABASE_URL` and the Stripe settings.

## How it is tested

pytest (`apps/billing/tests`):

- `test_celery.py`: `TestOnCelerySetupLogging` and
  `TestCeleryConfiguration` (queue, time zone, limit and schedule read from
  the settings);
- `test_tasks.py`: `TestStripeIdempotencyKey`, `TestIsPlaceholderStripeId`,
  `TestReportPendingUsage`, `TestReportPendingUsageScoping`,
  `TestCleanupOldUsageEvents` and `TestSyncAllProductsToStripe`, with mocked
  sessions and Stripe service.

behave (`apps/billing/features/background_tasks.feature`): the tasks are
executed eagerly (`Task.apply()`) against the in-memory database and the
mocked Stripe service, so no broker is needed:

- Pending usage events are reported to Stripe;
- The usage report sent to Stripe uses a key scoped to the SaaS app;
- Usage events without a subscription item fail;
- Old reported usage events are deleted;
- Products without a real Stripe identifier are pushed to Stripe;
- The beat schedule registers the periodic tasks;
- The beat schedule follows the configured intervals.
