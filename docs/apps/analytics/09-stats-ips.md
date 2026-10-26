# IP statistics

Two more routes of the statistics API show the traffic of single IP addresses:
a ranking of the most active addresses and the detail of one address. They
need the `analytics:read` scope like the other statistics routes.

## Endpoints

| Endpoint | Query parameters | Response |
| --- | --- | --- |
| `GET /api/v1/stats/ips` | `days` (30, 1 to 365), `limit` (50, 1 to 200) | List of `ip_address`, `sessions`, `pageviews`, `countries`, `browsers`, `device_types`, `first_seen`, `last_seen` |
| `GET /api/v1/stats/ips/{ip_address}` | `days` | One `IPDetailStats` object, or `404` |

### Ranking

`/ips` groups the sessions of the period by IP address, ordered by number of
sessions. Sessions without an IP address are ignored. For each address the
number of `pageview` events is counted with one extra query, and the distinct
countries, browsers and device types are listed (empty values are dropped).
`first_seen` and `last_seen` are the minimum and maximum of the sessions.

### Detail

`/ips/{ip_address}` accepts IPv4 and IPv6 addresses (the path parameter is
declared as `:path`, so the colons of IPv6 addresses are fine). It answers
`404 IP address not found` when the address has no session in the period. The
object contains:

- `total_sessions`, `total_pageviews`, `total_events`;
- the distinct `countries`, `cities`, `browsers`, `device_types`,
  `operating_systems` and `referrers`;
- `first_seen`, `last_seen`;
- `sessions_by_day`: one entry per UTC day with the number of sessions
  (`pageviews` is always `0` and `unique_visitors` always `1` in these entries);
- `pages`: the 50 most viewed pages (`pageview` events with a URL);
- `events`: the 50 most frequent event types, `pageview` excluded.

The ranking depends on the address stored with each session, so it follows the
`ANONYMIZE_IP` setting of the collection feature: with anonymization on, the
masked addresses are what you get here.

## PostgreSQL specifics

The distinct value lists are built with PostgreSQL's `array_agg`. The two
routes therefore need PostgreSQL; the other statistics routes use portable SQL.
The behave scenarios run on SQLite, so `features/environment.py` emulates
`array_agg` with `json_group_array` and decodes the result as a list.

## Tests

pytest (`test_routes_stats.py`): response models and one test class per route,
including the unknown address case.

behave (`features/stats_ips.feature`, seeded SQLite database, fake token
validator):

- IP statistics require the read scope
- Most active IP addresses
- The number of IP addresses can be limited
- Details of an IP address
- Details of an IPv6 address
- An unknown IP address is not found
- Sessions outside the period are ignored
