# Campaigns and pixels

A campaign groups the tracking of one mailing. A pixel is a 1x1 image bound to
one recipient of a campaign: when the mail client loads the image, the open is
recorded. This feature adds the campaign and pixel models, Alembic revision
`002`, the collector methods that create campaigns and pixels and record opens,
and the public pixel endpoints. Campaigns and pixels are created through the
collector service; the HTTP API that exposes that service is described in the
statistics pages.

## Endpoints

| Endpoint | Method | Description |
| --- | --- | --- |
| `/p/{pixel_key}.gif` | GET | Record an open and answer a transparent GIF |
| `/p/{pixel_key}` | GET | Same, without the extension (fallback) |

Usage in an email:

```html
<img src="https://analytics.example.com/p/{pixel_key}.gif" width="1" height="1" alt="">
```

The endpoints are public. They always answer `200` with the same 43 byte GIF,
whether the pixel exists or not, so that the response does not reveal which
keys are valid. The headers prevent caching (`Cache-Control` from
`PIXEL_CACHE_CONTROL`, `Pragma: no-cache`, `Expires: 0`) and set
`X-Content-Type-Options: nosniff`, because every open must reach the server.

## What is recorded

`CollectorService.track_pixel_open` looks the pixel up by key. For a known
pixel it:

- inserts a `PixelOpen` row with the client IP (proxy header and
  `ANONYMIZE_IP` as for collection), the user agent, and the GeoIP country and
  city;
- sets `first_opened_at` on the first open, always refreshes `last_opened_at`
  and increments `open_count`.

An unknown key logs a warning and records nothing.

`create_campaign(name, description, destination_url, extra_data)` and
`create_pixel(campaign_id, recipient_email, recipient_id, extra_data)` generate
the random URL-safe `tracking_key` and `pixel_key` (`secrets.token_urlsafe`).

## Data model

| Table (model) | Content |
| --- | --- |
| `analytics_campaigns` (`Campaign`) | `name`, `description`, unique `tracking_key`, `destination_url`, `extra_data` (JSONB), `is_active`, `created_at`, `updated_at`, denormalised counters `click_count` and `unique_click_count` (written by the link feature) |
| `analytics_pixels` (`Pixel`) | `campaign_id` (cascade), `recipient_email`, `recipient_id`, unique `pixel_key`, `extra_data`, `created_at`, `first_opened_at`, `last_opened_at`, `open_count` |
| `analytics_pixel_opens` (`PixelOpen`) | `pixel_id` (cascade), `opened_at` (indexed), `ip_address`, `user_agent`, `country`, `city` |

Deleting a campaign deletes its pixels, and deleting a pixel deletes its opens,
in the database (`ON DELETE CASCADE`) and in the ORM relationships.

## Migration

Revision `002` creates the three tables and their indexes. Databases that were
created by the original single `001` revision of the service already contain
these tables, so the revision creates each table only when it does not exist.
When Alembic renders offline SQL (`--sql`) it cannot inspect a database and
renders every statement.

```bash
uv run --package analytics alembic -c apps/analytics/alembic.ini upgrade head
```

## Tests

pytest:

- `test_services_collector.py`: pixel open for known and unknown pixels,
  `first_opened_at` set once, unknown client IP stored as null, campaign and
  pixel creation.
- `test_routes_pixel.py`: both endpoints for known and unknown keys and the
  request logging context.
- `test_models.py`: campaign, pixel and open models, unique keys, counter
  defaults and cascades.
- `test_migrations.py`: revision chain `001` to `002`, rendered SQL for the new
  tables and the skip logic for existing tables.
- `test_main.py`: both routes are registered.

behave (`features/pixel.feature`, through the ASGI application and the
temporary SQLite database):

- Campaign tracking keys are unique
- Opening a pixel returns a transparent GIF
- An open is recorded
- Each open increments the counter
- The pixel is also served without the gif extension
- The open records the client
- An unknown pixel still returns a GIF
- Deleting a campaign deletes its pixels and their opens
