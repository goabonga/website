# Campaign links

A campaign link is a short URL that counts the click and then redirects the
visitor to the real destination. It is meant for links in emails and marketing
material, next to the pixels of the previous page. This feature adds the
`CampaignClick` model, Alembic revision `003`, the click recording in the
collector service and the public redirect endpoint.

## Endpoint

| Endpoint | Method | Description |
| --- | --- | --- |
| `/t/{tracking_key}` | GET | Record a click and redirect with `302` |

```text
https://analytics.example.com/t/{tracking_key}
https://analytics.example.com/t/{tracking_key}?url=https://example.com/other
```

The endpoint is public. The status is always `302` (a temporary redirect, so
every click reaches the server).

### Destination

The destination is chosen in this order:

1. the `url` query parameter, when present (override);
2. the `destination_url` of the campaign;
3. a built-in fallback page, with a warning in the logs, when the key is
   unknown, the campaign is inactive or has no destination.

The `utm_source`, `utm_medium`, `utm_campaign`, `utm_term` and `utm_content`
parameters of the request are copied to the destination. When `utm_content` is
not given and the campaign exists, the tracking key is used as `utm_content`.
The parameters are appended with `?`, or with `&` when the destination already
has a query string.

The `url` override is not restricted to a list of hosts: anyone who knows a
tracking key, or any value, can build a redirect to an arbitrary URL on the
service's domain. Treat the endpoint as an open redirect when assessing risk.

## What is recorded

`CollectorService.track_campaign_click` only handles active campaigns
(`is_active`). For a match it inserts a `CampaignClick` row (client IP with the
proxy header and `ANONYMIZE_IP` rules, user agent, `Referer`, GeoIP country and
city) and increments `click_count` of the campaign. `unique_click_count` is
declared in the model and the table but is never updated: the code does not
check whether the IP clicked before.

An unknown or inactive key records nothing.

## Data model

`analytics_campaign_clicks` (model `CampaignClick`): `campaign_id` (foreign key
to `analytics_campaigns`, `ON DELETE CASCADE`, indexed), `clicked_at` (indexed),
`ip_address`, `user_agent`, `country`, `city`, `referrer`. The `Campaign` model
gets the `clicks` relationship, so deleting a campaign deletes its clicks.

Revision `003` creates the table, again only when it does not already exist
(databases created by the original single `001` revision have it).

## Tests

pytest:

- `test_services_collector.py`: click recorded for an active campaign, unknown
  campaign, unknown client IP stored as null and a missing referrer.
- `test_routes_track.py`: campaign destination, URL override, fallback, UTM
  propagation, `utm_content` kept when given, `&` after an existing query,
  campaigns without destination and the request logging context.
- `test_models.py`: click model and its cascade.
- `test_migrations.py`: revision chain `001` to `003` and the SQL of the new
  table.
- `test_main.py`: the route is registered.

behave (`features/track.feature`, through the ASGI application and the
temporary SQLite database):

- A campaign link redirects to its destination
- A click is recorded
- The click records the client and the referrer
- UTM parameters of the request are preserved
- Query parameters are appended to a destination that already has some
- The destination can be overridden with the url parameter
- An inactive campaign is not tracked
- An unknown key redirects to the fallback page
- An unknown key can still use the url override
- Deleting a campaign deletes its clicks
