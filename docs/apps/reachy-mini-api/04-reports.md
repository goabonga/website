# Reports and notifications

Endpoints used by the robot to fetch what it should announce. They are
protected by the scopes of the [JWT authentication](03-jwt-auth.md).

## Endpoints

All endpoints are mounted under `/api/reports` and appear in the OpenAPI
schema (when `DOCS_ENABLED` is true) under the `reports` tag.

| Endpoint | Scope | Response |
| --- | --- | --- |
| `GET /api/reports/daily` | `reachy:reports:read` | `DailyReport`: `date`, `summary`, `tasks_completed`, `tasks_pending`, `notifications`, `weather`, `calendar_events` |
| `GET /api/reports/quick` | `reachy:reports:read` | `QuickUpdate`: `message`, `priority` (`low`, `normal`, `high`), `category` |
| `GET /api/reports/notifications` | `reachy:notifications:read` | `count` and a list of `{id, message, read}` |

Every call writes an `ACTION: get_daily_report`, `get_quick_update` or
`get_notifications` line with the user id in the logs (see
[Dual-stream logging](02-logging.md)).

The endpoints currently return static placeholder data: the original code base
marks the real data aggregation as a TODO, so the content (five completed
tasks, three pending, two notifications, the sample weather and calendar
events) is fixed. Only the date of the daily report is computed.

Responses to unauthenticated or unauthorized calls follow the
authentication feature: 401 without a valid token, 403 when the scope is
missing, 503 while `OAUTH2_ISSUER` is not configured.

## Settings

No setting of its own. The scopes are read from the validated token.

## Data model

None.

## How it is tested

Pytest (`test_api_reports.py`): the three handlers called directly (payload
and audit log line), the response models, the routes mounted under `/api`,
and HTTP calls through `TestClient` with the JWT validation faked (missing
token, right scope, wrong scope, wildcard scope).

Behave (`apps/reachy-mini-api/features/reports.feature`), where the
`Given I am authenticated with scope "..."` step fakes the JWT validation so
that the token carries exactly that scope:

- Reports require authentication
- Reports require the reports scope
- Get the daily report
- Get a quick update
- Get the notifications
- Notifications require their own scope
