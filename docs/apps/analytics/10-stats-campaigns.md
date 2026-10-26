# Campaign statistics

The read side of the campaign tracking: how many pixels, opens and clicks each
campaign has, the clicks of one campaign over time, and the pixels of a
campaign. The routes need the `analytics:read` scope. Creating campaigns and
pixels through the API is the next page.

## Endpoints

| Endpoint | Query parameters | Response |
| --- | --- | --- |
| `GET /api/v1/stats/campaigns` | `include_inactive` (false), `limit` (50, 1 to 200) | List of `CampaignStats` |
| `GET /api/v1/stats/campaigns/{campaign_id}` | `days` (30, 1 to 365) | `CampaignDetail`, `404 Campaign not found` |
| `GET /api/v1/stats/campaigns/{campaign_id}/pixels` | `limit` (100, 1 to 500), `offset` (0) | List of `PixelStats`, `404 Campaign not found` |

`campaign_id` must be a UUID, otherwise the answer is `422`.

### `GET /campaigns`

Campaigns ordered by creation date, newest first. Inactive campaigns are
hidden unless `include_inactive=true`. Each `CampaignStats` has `id`, `name`,
`tracking_key`, `is_active`, `click_count`, `unique_click_count`,
`pixel_count`, `total_opens` (the sum of `open_count` of the campaign's pixels)
and `created_at`. The counters of pixels and opens are computed with two extra
queries per campaign.

`unique_click_count` is always `0`: the click tracking increments `click_count`
only (see the campaign links page).

### `GET /campaigns/{campaign_id}`

`CampaignDetail` adds the description, the destination URL and `updated_at` to
the counters of the list, plus two breakdowns over the last `days` days:

- `clicks_by_day`: per UTC day, `sessions` is the number of clicks and
  `unique_visitors` the number of distinct IP addresses (`pageviews` is
  always `0`);
- `clicks_by_country`: the ten countries with most clicks and their share of
  the clicks of the period. Clicks without a known country are grouped under a
  `null` country.

`click_count` is the all-time counter of the campaign; the breakdowns only
cover the requested period.

### `GET /campaigns/{campaign_id}/pixels`

The pixels of the campaign, newest first, with `id`, `pixel_key`,
`recipient_email`, `recipient_id`, `open_count`, `first_opened_at`,
`last_opened_at` and `created_at`. Use `limit` and `offset` to paginate.

## Tests

pytest (`test_routes_stats.py`, mocked database session): the campaign and
pixel response models and one test class per route, including the
`include_inactive` flag, pixels without opens and the `404` answers. Pagination
is covered by the behave scenarios only.

behave (`features/stats_campaigns.feature`): campaigns, pixels, opens and clicks
are created through the real tracking endpoints (`/p/...`, `/t/...`) and read
back through the statistics API on the temporary SQLite database:

- Campaign statistics require the read scope
- Campaigns are listed with their counters
- Inactive campaigns are hidden by default
- Inactive campaigns can be included
- The number of campaigns can be limited
- Campaign detail
- An unknown campaign is not found
- A campaign identifier must be a UUID
- Pixels of a campaign
- Pixels can be paginated
- Pixels of an unknown campaign are not found
