# Usage reporting

Services and agents report what they did so that the activity of a team can be
audited and billed: each reported event is stored as a row of the execution log
of the team (the table created with [Tasks](09-tasks.md)). This feature adds the
two reporting endpoints. They need the `team:write` scope, which is meant for
service accounts (machine clients) rather than for the platform administrators.

## Endpoints

Routes are under `/usage/{team_id}` and check that the team exists
(`404 Team not found`).

| Method | Path | Scope | Description |
|--------|------|-------|-------------|
| POST | `/usage/{team_id}/report` | `team:write` | Report one event (`201`), returns the stored event |
| POST | `/usage/{team_id}/batch` | `team:write` | Report 1 to 100 events at once (`201`), returns `{"created": <number>}` |

An event has an `agent_id` (required), an optional `task_id`, an `action`
(required, up to 100 characters, for example `task.completed`; it is stored as
the `event_type` of the log entry), a free-form `details` object and an
optional `timestamp`. Without a timestamp the current UTC time is used. A
timestamp that carries a time zone is stored with the zone removed, without
converting the time: `2026-03-01T10:00:00+02:00` is stored as
`2026-03-01T10:00:00`. The response of `/report` returns `id`, `team_id`,
`agent_id`, `task_id`, `action`, `details`, `timestamp` and `created_at`.

An empty batch, a batch of more than 100 events or an action longer than 100
characters is refused with `422`.

## Data model and migration

No new table: events are rows of `execution_logs` (model `ExecutionLog`,
schemas `UsageReport`, `UsageBatchReport`, `UsageEventResponse`). The
migration of the log is `0007_create_tasks`.

## Settings

No new setting.

## Tests

pytest: `tests/test_routes_usage.py` covers both endpoints (single and batch
reports, timestamp handling, unknown team, validation, scope and
authentication) and `tests/test_schemas.py` covers the usage schemas.

behave (`features/usage.feature`):

- Reporting a usage event
- An event keeps the timestamp it was reported with
- An event without timestamp is stamped with the current time
- Reporting several events at once
- A batch needs at least one event
- An action is limited to 100 characters
- Reporting usage for an unknown team
- Reporting usage needs the team:write scope

The shared steps gain "the response JSON field ... is not empty".
