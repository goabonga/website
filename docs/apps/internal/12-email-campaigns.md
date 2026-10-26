# Email campaigns

E-mail campaigns tie an email template to a contact group and send it through a mail provider.
Operators can create and schedule campaigns, start, pause and resume them, and follow
delivery statistics. Campaigns are stored and executed by the mailler service; the pages use the
mailler client. This feature builds on the contact, group and template features.

## What it adds

| Module | Role |
| --- | --- |
| `internal/models/email_campaign.py` | Email campaign and send tracking models. |
| `internal/routes/email_campaigns.py` | Email Campaigns CRUD routes for sending emails. |

It also ships 3 Jinja2 template(s) under `internal/templates/` (packaged with the wheel).

## Endpoints

| Method | Path | Required scope | Description |
| --- | --- | --- | --- |
| GET | /email-campaigns | `email_campaigns:read` | List all email campaigns with pagination and filtering. |
| GET | /email-campaigns/new | `email_campaigns:write` | Show form to create a new email campaign. |
| POST | /email-campaigns/new | `email_campaigns:write` | Create a new email campaign. |
| POST | /email-campaigns/bulk-delete | `email_campaigns:delete` | Delete multiple email campaigns at once. |
| GET | /email-campaigns/{campaign_id} | `email_campaigns:read` | View email campaign detail with statistics. |
| GET | /email-campaigns/{campaign_id}/edit | `email_campaigns:write` | Show form to edit an email campaign. |
| POST | /email-campaigns/{campaign_id}/edit | `email_campaigns:write` | Update an email campaign. |
| POST | /email-campaigns/{campaign_id}/send | `email_campaigns:send` | Start sending an email campaign. |
| POST | /email-campaigns/{campaign_id}/pause | `email_campaigns:send` | Pause a sending campaign. |
| POST | /email-campaigns/{campaign_id}/resume | `email_campaigns:send` | Resume a paused campaign. |
| POST | /email-campaigns/{campaign_id}/delete | `email_campaigns:delete` | Delete an email campaign. |
| GET | /email-campaigns/{campaign_id}/stats | `email_campaigns:read` | Get campaign statistics as JSON (for AJAX updates). |

The list and detail pages request the whole `email_campaigns` resource plus `vpn:admin` and `billing:read` (navigation).

## Pages and life cycle

- **List** (`/email-campaigns`): filterable by campaign status (`draft`, `scheduled`, `sending`,
  `paused`, `completed`, `failed`) and search.
- **Create and edit** (`/email-campaigns/new`, `/{id}/edit`): name, description, template, contact
  group, provider ("Use default provider" leaves the choice to the mailler service, which applies
  the provider of the campaign's client), sender name and address, reply-to and an optional
  schedule time.
- **Detail** (`/email-campaigns/{id}`): the provider of the campaign (`MAILLER_DEFAULT_PROVIDER`
  for a campaign that names none, "Client default" when that setting is empty), statistics and the individual sends, whose status is one of
  `pending`, `queued`, `sent`, `delivered`, `opened`, `clicked`, `bounced`, `complained` or `failed`.
  `GET /email-campaigns/{id}/stats` returns the same statistics as JSON for the page's
  live refresh.
- **Send, pause, resume** (`POST /{id}/send|pause|resume`): need `email_campaigns:send`. A campaign
  can only be sent from `draft` or `scheduled`; the mailler service validates the template, the group and
  the recipients, and its error message is shown back on the detail page (`MaillerAPIError`).
- **Delete** (single and bulk): needs `email_campaigns:delete`. A failed creation or update redirects
  back to the form with an `error` message, which the form shows. The providers of the form are the names
  the mailler service returns.

## Data model

`EmailCampaign` and `EmailSend` describe the mailler service's campaign and per-recipient send
tables, with relationships to the contact, group and template models of the previous features.
The pages themselves read campaigns through the mailler API.

**`EmailCampaign`** maps the `email_campaigns` table: `id`, `name`, `description`, `template_id`, `group_id`, `status`, `scheduled_at`, `started_at`, `completed_at`, `total_recipients`, `sent_count`, `delivered_count`, `opened_count`, `clicked_count`, `bounced_count`, `complained_count`, `failed_count`, `from_name`, `from_email`, `reply_to`, `provider`, `subject_override`, `metadata_`, `task_id`, `analytics_campaign_id`, `analytics_tracking_key`, `created_at`, `updated_at`.

**`EmailSend`** maps the `email_sends` table: `id`, `campaign_id`, `contact_id`, `recipient_email`, `recipient_name`, `status`, `queued_at`, `sent_at`, `delivered_at`, `opened_at`, `clicked_at`, `bounced_at`, `error_message`, `smtp_response`, `message_id`, `analytics_pixel_key`, `metadata_`, `created_at`.

`CampaignStatus` and `EmailSendStatus` are string enums matching the statuses above. No migrations are shipped.

## Tests

pytest:

- `tests/routes/test_email_campaigns.py`
- `tests/routes/test_email_campaigns_sidebar.py`

The tests cover each route handler (life-cycle guards, error propagation, JSON statistics, bulk delete) the properties of the campaign models and the provider label of the detail page rendered for real. The forms are tested for the error message of a failed save.

`tests/routes/test_email_campaigns_sidebar.py` opens every page of this feature through the application with its real templates (throw-away SQLite database, mocked service clients) and, for each scope combination, checks the sidebar: exactly the links the scopes permit, a single active link and the signed-in user.

Behave scenarios, run in-process with `uv run --package internal behave apps/internal/features` (`features/email_campaigns.feature`):

- List email campaigns
- List email campaigns unauthenticated
- List email campaigns with search filter
- List email campaigns with status filter
- View new campaign form
- Create a new campaign successfully
- Create a new campaign failure
- View campaign detail
- View campaign detail not found
- View campaign edit form
- View campaign edit form for sending campaign is blocked
- Update a campaign successfully
- Update a campaign failure
- Send a draft campaign
- Send a campaign that is not in draft or scheduled status
- Pause a sending campaign
- Pause a campaign that is not sending
- Resume a paused campaign
- Resume a campaign that is not paused
- Delete a draft campaign
- Delete a sending campaign is blocked
- Delete a campaign not found
- Bulk delete campaigns
- Bulk delete with no selection
- Get campaign stats JSON
- Get campaign stats for non-existent campaign
- Sidebar on the email campaigns list
- Sidebar on the new email campaign form
- Sidebar on the email campaign detail
- Sidebar on the email campaign edit form
- Sidebar gated links follow the scopes on the email campaigns list

The mailler client is replaced by an `AsyncMock`; scenarios cover listing, create and edit, sending and pausing, error propagation and unauthorized access.

Browser scenarios, run in Chromium against the application served on a local socket (`features/browser/email_campaigns.feature`, `uv run --package internal --group dev behave apps/internal/features -t @browser`):

- The campaigns are listed
- The Email Campaigns link leads to the list
- A user without the campaign scope gets the access denied page
- An anonymous visitor comes back to the page asked for after the login
- The campaigns are filtered by status
- The search is kept in the address
- A campaign is created from the form
- The providers are listed by name
- The form requires a name, a template and a group
- A campaign the mailler service refuses is reported on the form
- The list leads to the detail of a campaign
- A campaign that does not exist sends the user back to the list
- A campaign is updated from its edit form
- A campaign the mailler service cannot update is reported on the form
- A campaign that is being sent cannot be edited
- A draft campaign is started after a confirmation
- Dismissing the confirmation does not start the campaign
- A sending campaign is paused
- A paused campaign is resumed
- A sending campaign cannot be deleted
- A draft campaign is deleted after a confirmation
- Selected campaigns are deleted in bulk

The status of the campaign decides which buttons the detail page offers (start, pause, resume), starting asks for a confirmation, and the providers of the form are listed by name.
