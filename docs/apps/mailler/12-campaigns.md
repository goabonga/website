# Email campaigns

A campaign sends one [template](08-templates.md) to every active contact of a
[contact group](10-contact-groups.md), immediately or at a scheduled time,
and tracks each individual send.

Campaigns are owned by a client (see [client identity](02-authentication.md)):
a client only sees and drives its own campaigns, and a campaign can only use
the template and the group of its own client. Administrators can act on every
client.

## Endpoints

All routes live under `/api/v1/campaigns`.

| Endpoint | Method | Scope | Description |
| --- | --- | --- | --- |
| `/campaigns` | GET | `mailler:read` | Paginated list of the client's campaigns (`page`, `page_size`, `status`, `search` on the name; `client_id` for administrators) |
| `/campaigns` | POST | `mailler:write` | Create a draft campaign (`201`); administrators may pass `client_id` to create it for another client |
| `/campaigns/{id}` | GET | `mailler:read` | Read a campaign with its counters and rates |
| `/campaigns/{id}` | PUT | `mailler:write` | Update a `draft` or `scheduled` campaign |
| `/campaigns/{id}` | DELETE | `mailler:write` | Delete (`204`), refused while `sending` |
| `/campaigns/{id}/schedule` | POST | `mailler:send` | Schedule at `scheduled_at` |
| `/campaigns/{id}/send` | POST | `mailler:send` | Start sending now |
| `/campaigns/{id}/pause` | POST | `mailler:send` | Pause a sending campaign |
| `/campaigns/{id}/resume` | POST | `mailler:send` | Resume a paused campaign |
| `/campaigns/{id}/preview` | GET | `mailler:read` | Render the template with sample data |
| `/campaigns/{id}/sends` | GET | `mailler:read` | Paginated list of the individual sends (`status` filter) |

A campaign references a template (`template_id`) and a group (`group_id`),
and may override the subject (`subject_override`), sender (`from_email`,
`from_name`, `reply_to`) and `provider`. An unknown template or group, or one
that belongs to another client, gives `404`, and so does a campaign of
another client.

The sender defaults to `DEFAULT_FROM` / `DEFAULT_FROM_NAME` and the provider
to `DEFAULT_PROVIDER`; there is no built-in provider. A campaign that ends up
with neither a sender address nor a provider is marked `failed` by the worker.

## Lifecycle

`draft` -> `scheduled` -> `sending` -> `completed`, with `paused` and
`failed` as side states.

- `schedule` and `send` need a template and a group (`400` otherwise); `send`
  also needs at least one active contact in the group. Both are refused for
  campaigns that are not in an allowed status.
- `send` moves the campaign to `sending`, records `total_recipients` and
  queues `send_campaign_task`; `pause` and `resume` switch between `sending`
  and `paused` (`resume` queues the task again).
- The campaign is `completed` once every contact has been queued.

## Worker tasks

- `send_campaign_task(campaign_id)` (queue `CELERY_QUEUE`) loads the campaign and,
  for every active contact of the campaign's client in the group that has not
  been processed yet,
  renders the subject, HTML and plain text with the Jinja2 sandbox of the
  [templates](08-templates.md) feature (HTML values are escaped, the subject
  and the plain text are not), creates an
  `EmailSend` row and an `Email` row (owned by the campaign's client,
  `metadata` carrying the campaign and send identifiers) and queues
  [`send_email_task`](04-send.md). The template context contains `email`,
  `first_name`, `last_name`, `full_name`, `unsubscribe_url` (the signed link
  of the [unsubscribe](11-unsubscribe.md) feature, bound to the campaign's
  client) and the contact's custom fields. Plain text templates may use `%variable%` instead of
  `{{ variable }}`. The status is re-checked every `CAMPAIGN_BATCH_SIZE` contacts so a pause
  stops the run. A campaign that is not `sending` is skipped, one without
  template or group, or whose template does not compile, is marked `failed`.
  A contact whose rendering fails (for example a template reaching for Python
  internals) is counted as failed and the others go on.
- When an email is sent or fails for good, `send_email_task` updates the
  matching `EmailSend` and the campaign counters.
- `check_scheduled_campaigns` (every minute, in the beat schedule) starts the
  `scheduled` campaigns that are due and have active contacts.

## Data model and migration

Alembic revision `004` creates `email_campaigns` (required indexed
`client_id`, status, template and group
references, sender overrides, schedule and lifecycle timestamps, counters:
`total_recipients`, `sent_count`, `delivered_count`, `opened_count`,
`clicked_count`, `bounced_count`, `complained_count`, `failed_count`) and
`email_sends` (one row per recipient with its own status: `pending`,
`queued`, `sent`, `delivered`, `opened`, `clicked`, `bounced`, `complained`,
`failed`). The campaign model exposes derived `progress_percent`,
`open_rate`, `click_rate`, `bounce_rate` and `complaint_rate`. Delivery events
from the provider update these rows through the
webhooks feature.

## Settings

| Variable | Default | Description |
| --- | --- | --- |
| `CAMPAIGN_BATCH_SIZE` | `50` | Contacts processed between two checks for a pause |
| `DEFAULT_PROVIDER` | empty | Optional platform provider used when a campaign names none |

The sender defaults are the `DEFAULT_FROM` settings of the
[providers](03-providers.md) page.

## How it is tested

- pytest: `tests/test_routes_campaigns.py`, the campaign parts of
  `tests/test_tasks_send.py` and `tests/test_tasks_scheduler.py`, the campaign
  model cases in `tests/test_models.py`, the beat schedule in
  `tests/test_celery_config.py`.
- behave: `features/campaigns.feature` covers the API (listing, creation,
  update, delete, schedule, send, pause and resume guards, preview, sends,
  scopes) and runs the worker tasks end to end against the in-process
  SQLite database: one personalised email per active contact (unsubscribed
  contacts are left out), the platform provider fallback, a campaign without
  provider failing, skipped campaigns and the scheduler starting due
  campaigns; the isolation scenarios check that a client cannot see, drive or
  borrow the template and group of another client. `send_email_task` and `send_campaign_task` are replaced by
  recorders, so nothing is delivered.
