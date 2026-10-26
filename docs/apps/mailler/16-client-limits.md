# Client sending limits

Each [authorized client](15-authorized-clients.md) can be given a rate limit
and a daily quota so that one application cannot flood the service or the
providers. Both are optional: a client without limits is unlimited.

## The limits

| Field | Meaning |
| --- | --- |
| `rate_limit_per_minute` | Emails the client may have created during the last 60 seconds |
| `daily_quota` | Emails the client may have created since 00:00 UTC |

Both are set through the registry API (`POST` and `PUT /api/v1/clients`) and
must be positive integers; sending `null` on update removes a limit.

## What is counted and refused

- Emails are counted from the `emails` table by `client_id` and creation time,
  so the figures are shared by every API process and include scheduled emails,
  emails sent from a template and the emails of campaigns. The table
  has an index on `(client_id, created_at)` for this.
- `POST /send` and `POST /schedule` count one email. A request that would take
  the client over the rate limit or the quota is refused with `429`, nothing
  is stored, and the `Retry-After` header tells how many seconds to wait (60
  for the rate limit, the time left until midnight UTC for the quota).
- Starting a campaign (`POST /campaigns/{id}/send`) counts all its recipients
  against the daily quota only; the rate limit does not apply to campaigns,
  which are paced by the worker. The campaign stays a draft when refused.
- Administrators are never limited.
- The check is not atomic: requests handled at the same moment can overshoot a
  limit by a few emails.

## Data model and migration

Alembic revision `007` adds the two nullable columns to `authorized_clients`
and creates the index `ix_emails_client_id_created_at`. Existing clients stay
unlimited. The steps check whether they are needed, so the migration can be
run again.

## How it is tested

- pytest: the `enforce_limits` cases of `tests/test_services_clients.py`
  (windows, counts, both limits, `Retry-After`, administrators), the limit
  cases of the send, schedule and campaign route tests,
  `tests/test_routes_clients.py`, `tests/test_models_client.py` and
  `tests/test_migration_client_limits.py` (the `007` upgrade and downgrade on
  SQLite).
- behave: `features/client_limits.feature` (rate limit, isolation between
  clients, the one-minute and one-day windows, quota for scheduled emails and
  campaigns, administrators, management through the API) against the
  in-process SQLite database. The migration was not run on PostgreSQL.
