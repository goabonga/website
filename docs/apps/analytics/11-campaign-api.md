# Campaign management

Campaigns and pixels used to be created only through the collector service.
This feature exposes them over HTTP, so that a mailing tool can create the
tracking links and pixels of a mailing. The routes belong to the statistics
router and need the `analytics:write` scope (`403` with a read-only token).

## Endpoints

| Endpoint | Body | Success | Errors |
| --- | --- | --- | --- |
| `POST /api/v1/stats/campaigns` | `CampaignCreate` | `201` `CampaignResponse` | `422` invalid body |
| `POST /api/v1/stats/campaigns/{campaign_id}/pixels` | `PixelCreate` | `201` `PixelResponse` | `404 Campaign not found` |
| `POST /api/v1/stats/campaigns/{campaign_id}/pixels/batch` | `PixelBatchCreate` | `201` `PixelBatchResponse` | `404 Campaign not found` |
| `DELETE /api/v1/stats/campaigns/{campaign_id}` | none | `204` | `404 Campaign not found` |

### Create a campaign

```bash
curl -X POST https://analytics.example.com/api/v1/stats/campaigns \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"name": "Spring sale", "destination_url": "https://example.com/spring"}'
```

`name` is required; `description`, `destination_url` and `extra_data` (a JSON
object stored as is) are optional. The answer contains the `id`, the generated
`tracking_key`, `is_active` and `created_at`. The tracking link of the campaign
is `/t/{tracking_key}` (see the campaign links page).

### Create pixels

`PixelCreate` has the optional fields `recipient_email`, `recipient_id` and
`extra_data`. The answer contains the `id`, the generated `pixel_key`, the
`campaign_id`, the recipient fields and `created_at`; the pixel URL is
`/p/{pixel_key}.gif`.

The batch route takes `{"pixels": [PixelCreate, ...]}` and answers the
`campaign_id`, `created_count` and the list of created pixels. The pixels are
created one after the other and each one is committed on its own: if a
request fails midway (for example with a database error) the pixels created
so far are kept. The batch size is not limited.

### Delete a campaign

Deleting a campaign removes it with its pixels, their opens and its clicks
(database cascade and ORM relationships). The operation cannot be undone and
there is no soft delete: to stop tracking while keeping the data, the
`is_active` flag of the campaign has to be cleared in the database, since no
route updates a campaign.

## Tests

pytest (`test_routes_stats.py`, mocked database session): request and response
models, and one test class per route with the success path and the `404`
answers.

behave (`features/campaign_api.feature`, fake token validator, temporary
SQLite database):

- Creating a campaign requires the write scope
- Create a campaign
- A campaign needs a name
- The tracking link of a new campaign works
- Create a pixel for a campaign
- The pixel of a new recipient records opens
- Pixels cannot be created for an unknown campaign
- Create several pixels at once
- Batch creation is refused for an unknown campaign
- Delete a campaign with its pixels
- Deleting an unknown campaign is not found
- Deleting a campaign requires the write scope
