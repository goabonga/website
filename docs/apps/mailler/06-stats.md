# Sending statistics

Aggregated delivery counters computed in real time from the stored emails
of the calling client (see [client identity](02-authentication.md));
administrators get the counters of every client.

## Endpoint

| Endpoint | Method | Scope | Description |
| --- | --- | --- | --- |
| `/api/v1/stats` | GET | `mailler:stats` | Totals, per-provider and per-day counters |

Query parameters:

| Parameter | Default | Description |
| --- | --- | --- |
| `start_date` | 30 days before `end_date` | First day to include (ISO date) |
| `end_date` | today | Last day to include (ISO date) |
| `provider` | none | Restrict the statistics to one provider |
| `client_id` | none | Administrators only: restrict the statistics to one client. Any other caller asking for a client other than its own gets `403` |

An invalid date gives `422`. Emails are selected on `created_at` within the
range (the whole of both days, in UTC).

## Response

```json
{
  "total": {"sent": 0, "delivered": 0, "bounced": 0, "failed": 0},
  "by_provider": {"brevo": {"sent": 0, "delivered": 0, "bounced": 0, "failed": 0}},
  "by_date": [{"date": "2026-01-27", "sent": 0, "delivered": 0, "bounced": 0, "failed": 0}]
}
```

Each counter counts the emails currently in that status (`sent`, `delivered`,
`bounced`, `failed`); emails that are still `pending` or `queued` are not
counted. `by_provider` only contains providers that have emails in the range
and `by_date` is ordered by day.

These figures come from the `emails` table. The separate `provider_stats`
table, maintained by the delivery task, is not read by this endpoint.

## How it is tested

- pytest: `tests/test_routes_stats.py`, plus routing cases in
  `tests/test_main.py`.
- behave: `features/stats.feature` seeds emails in the in-process SQLite
  database and checks totals, the provider and day breakdowns, the provider
  filter, the date range, validation, authentication and scope, and the
  isolation between clients (own emails only, foreign filter `403`,
  administrator view).
