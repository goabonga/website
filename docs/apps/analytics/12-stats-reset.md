# Data reset

The last route of the statistics API erases every analytics table. It is meant
for administrators, for example to clear test data after a deployment.

## Endpoint

| Endpoint | Scope | Response |
| --- | --- | --- |
| `DELETE /api/v1/stats/reset` | `analytics:delete` | `ResetResponse` |

```bash
curl -X DELETE https://analytics.example.com/api/v1/stats/reset \
  -H "Authorization: Bearer $TOKEN"
```

The scope `analytics:delete` is separate from `analytics:read` and
`analytics:write`: a token that only reads or writes gets `403`, a request
without a token `401`. The scope is granted by the authorization server, the
service does not define roles of its own.

## What it does

In a single transaction the route deletes, in this order, the rows of
`analytics_pixel_opens`, `analytics_campaign_clicks`, `analytics_pixels`,
`analytics_campaigns`, `analytics_events` and `analytics_sessions`, then
commits. The answer reports how many rows were deleted per table:

```json
{
  "success": true,
  "sessions_deleted": 10,
  "events_deleted": 50,
  "campaigns_deleted": 2,
  "pixels_deleted": 5,
  "clicks_deleted": 20,
  "pixel_opens_deleted": 30
}
```

Calling it on an empty database succeeds and reports zeros. The deletion
cannot be undone and the route does not ask for a confirmation, so keep the
`analytics:delete` scope for people and clients that really need it.

## Tests

pytest (`test_routes_stats.py`): the `ResetResponse` model and the route with
a mocked database session (counts per table, one commit).

behave (`features/stats_reset.feature`, fake token validator, temporary SQLite
database seeded through the real endpoints: one campaign, one pixel, one
session with an event, one pixel open and one click):

- Resetting requires the delete scope
- Resetting requires a token
- Reset deletes every analytics table
- Resetting an empty database deletes nothing
