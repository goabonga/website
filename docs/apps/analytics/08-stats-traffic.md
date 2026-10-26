# Traffic statistics

The first part of the secured statistics API turns the stored sessions and
events into the figures of a dashboard: totals, a daily series and top lists.
All routes live in `analytics.routes.stats` under the prefix `/api/v1/stats`
and need a bearer token that carries the scope `analytics:read` (see the
authentication page): `401` without a valid token, `403` without the scope,
`503` when `OAUTH2_ISSUER` is not set.

## Endpoints

| Endpoint | Query parameters | Response |
| --- | --- | --- |
| `GET /api/v1/stats/overview` | `days` | `total_sessions`, `unique_visitors`, `total_pageviews`, `total_events`, `period_start`, `period_end` |
| `GET /api/v1/stats/daily` | `days` | List of `date`, `sessions`, `pageviews`, `unique_visitors`, oldest day first |
| `GET /api/v1/stats/countries` | `days`, `limit` (10) | List of `country`, `sessions`, `percentage` |
| `GET /api/v1/stats/devices` | `days` | List of `device_type`, `sessions`, `percentage` |
| `GET /api/v1/stats/browsers` | `days`, `limit` (10) | List of `browser`, `sessions`, `percentage` |
| `GET /api/v1/stats/referrers` | `days`, `limit` (10) | List of `referrer`, `sessions`, `percentage` |
| `GET /api/v1/stats/pages` | `days`, `limit` (20) | List of `page_url`, `pageviews`, `unique_sessions` |
| `GET /api/v1/stats/events` | `days`, `limit` (20) | List of `event_type`, `count`, `unique_sessions` |

`days` is the length of the period ending now: default `30`, between `1` and
`365`. `limit` is between `1` and `100`. Values outside these bounds are
rejected with `422`.

## Definitions

- The period filters sessions on `first_seen`. Event counts include the events
  of those sessions, whatever the date of the event itself.
- A session counts as a visitor through its IP address: `unique_visitors` is
  the number of distinct IP addresses, so several people behind one address
  count once.
- A pageview is an event whose `event_type` is exactly `pageview`. The
  collection endpoints accept any event type, so the SDK or the beacon must
  send `pageview` for the pageview figures and the page ranking to count it.
- In the top lists, `percentage` is the share of the sessions of the period
  (two decimals). For referrers the base is the sessions that have a referrer,
  so direct visits are ignored. Sessions without a country, device or browser
  appear under a `null` entry.
- `/pages` ranks pageviews that have a `page_url`; `/events` ranks every event
  type.
- `/daily` groups by the UTC date. Days without sessions are not returned, and
  a day's pageviews come from the events of the sessions of the period grouped
  by event date.

## Tests

pytest (`test_routes_stats.py`, with a mocked database session and the
authentication dependencies overridden):

- `get_date_range`;
- the response models of this page;
- one test class per endpoint checking how query rows are mapped to the
  response, plus the null aggregate cases (overview, countries) and the empty
  daily series.

`test_main.py` also checks that the router is registered.

behave (`features/stats_traffic.feature`): the scenarios seed sessions and
events in the temporary SQLite database, authenticate with a fake token
validator (the real `require_scopes` dependency runs) and call the API through
the ASGI application:

- Statistics require a token
- Statistics require the read scope
- Overview of the last 30 days
- The period can be widened
- The period is validated
- Daily statistics
- Sessions by country
- The number of countries can be limited
- Sessions by device type
- Sessions by browser
- Sessions by referrer ignore direct visits
- Most visited pages count page views only
- Events by type
