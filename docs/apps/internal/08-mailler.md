# Mailler statistics

A read-only view of the platform's mail delivery statistics, plus the HTTP client for
the mailler service that the contact, template and campaign features reuse. Operators with
`mailler:read` get a statistics dashboard and a searchable list of the e-mails the
mailler service has handled.

## What it adds

| Module | Role |
| --- | --- |
| `internal/services/mailler_client.py` | Async HTTP client for Mailler API. |
| `internal/services/mailler_client_sync.py` | Synchronous HTTP client for Mailler API (for Celery tasks). |
| `internal/routes/mailler.py` | Mailler dashboard routes for HTML pages. |

It also ships 3 Jinja2 template(s) under `internal/templates/` (packaged with the wheel).

## Endpoints

| Method | Path | Required scope | Description |
| --- | --- | --- | --- |
| GET | /mailler | `mailler:read` | Mailler statistics dashboard. |
| GET | /mailler/emails | `mailler:read` | List all emails with pagination and filters. |
| GET | /mailler/emails/{email_id} | `mailler:read` | View email details. |

All three pages request the `mailler` resource (`read`, `write`, `delete`) plus `vpn:admin` and `billing:read` for the navigation, and only need `mailler:read` to open. The statistics call itself is made with the `mailler:stats` scope.

## Pages

- **Dashboard** (`/mailler?days=30&provider=`): delivery statistics for the last 1 to 365
  days, optionally filtered by provider.
- **E-mails** (`/mailler/emails`): paginated list (`page`, `page_size` up to 100) filterable by
  provider and by status (`pending`, `queued`, `sent`, `delivered`, `bounced`, `failed`).
- **E-mail detail** (`/mailler/emails/{id}`): one e-mail. The id must be a UUID; an invalid or
  unknown id redirects to the list with an error message.
- **Clients** (`/mailler/clients...`): the registry of the applications allowed to use the
  service, for holders of `mailler:admin`, see [Mailler clients](08a-mailler-clients.md).

## Mailler client

`internal.services.mailler_client.MaillerClient` (instance `mailler_client`) is the single
gateway to the mailler service. It uses the client-credentials grant with the narrowest scope per call
(`mailler:read`, `mailler:stats`, `mailler:write`, `mailler:send`), always together with the
administration scope (`MAILLER_ADMIN_SCOPE`), one cached token per scope set, and an optional
Unix socket transport (`MAILLER_SOCKET_PATH`).

The mailler service serves several applications and keeps their data apart: a regular client only
sees its own e-mails, statistics, templates, contacts, groups and campaigns, and must be registered
in the service's client registry. The administration scope (`ADMIN_SCOPE` of the service,
`mailler:admin` by default) lifts that boundary, which is what an admin application needs: the
dashboard and the e-mail list then cover every client, and the lists of the next features show the
data of all of them. Records created from this application are owned by its own OAuth client,
like any other client's. The OAuth client of this application must hold the scope at the identity
provider; with `MAILLER_ADMIN_SCOPE` empty it only sees what it owns. Besides the providers, statistics and e-mail
calls used on this page, it already wraps the template, contact, contact-group and campaign
endpoints that the next features use. Calls return plain dictionaries; failures are logged and
produce an empty result, `None` or `False`, except `send_campaign`, which raises `MaillerAPIError`
so that the campaign page can show the service's message.

`internal.services.mailler_client_sync.SyncMaillerClient` is the synchronous counterpart with
`get_providers` and `send_email` for Celery tasks; no task of this application uses it yet. It does
not request the administration scope: an e-mail sent through it goes out as a regular registered
client, with the sender and provider of its record.

## Settings

Read from environment variables (or a `.env` file) by `internal.config.Settings`.

| Variable | Default | Notes |
| --- | --- | --- |
| `MAILLER_API_URL` | empty | Mailler service URL over TCP (no default: unset, the calls return nothing) |
| `MAILLER_SOCKET_PATH` | empty | Unix socket path; takes precedence over the URL |
| `MAILLER_ADMIN_SCOPE` | `mailler:admin` | Administration scope, to set to the service's `ADMIN_SCOPE`; empty to act as an ordinary client |
| `MAILLER_TIMEOUT` | `30.0` | Seconds allowed per request |
| `MAILLER_DEFAULT_PROVIDER` | empty | Provider shown for a campaign that names none; empty shows that the provider of its mailler client applies |

## Tests

pytest:

- `tests/routes/test_mailler.py`
- `tests/services/test_mailler_client.py`
- `tests/services/test_mailler_client_sync.py`
- `tests/routes/test_mailler_sidebar.py`

The tests cover the three route handlers, both clients (token cache, socket transport, administration scope and timeout from the settings, every endpoint wrapper, error mapping) and the neutral defaults of the settings.

`tests/routes/test_mailler_sidebar.py` opens every page of this feature through the application with its real templates (throw-away SQLite database, mocked service clients) and, for each scope combination, checks the sidebar: exactly the links the scopes permit, a single active link and the signed-in user.

Behave scenarios, run in-process with `uv run --package internal behave apps/internal/features` (`features/mailler.feature`):

- View mailler dashboard
- View mailler dashboard unauthenticated
- View mailler dashboard with provider filter
- List emails
- List emails with filters
- View email detail when found
- View email detail when not found
- View email detail with invalid UUID
- Sidebar on the mailler dashboard
- Sidebar on the emails list
- Sidebar on the email detail
- Sidebar gated links follow the scopes on the mailler dashboard

The mailler client is replaced by an `AsyncMock`; scenarios cover the dashboard, filters, pagination, the detail page and its error redirects.

Browser scenarios, run in Chromium against the application served on a local socket (`features/browser/mailler.feature`, `uv run --package internal --group dev behave apps/internal/features -t @browser`):

- The dashboard shows the totals and the providers
- A user without the mailler scope gets the access denied page
- An anonymous visitor comes back to the dashboard after the login
- Changing the period reloads the dashboard
- Choosing a provider restricts the statistics to it
- The dashboard links to the list of emails
- The emails are listed with their status
- The emails are filtered by provider and by status
- The number of emails per page can be changed
- The emails are paginated
- The filters are kept when moving to another page
- The list leads to the detail of an email
- An email that does not exist sends the user back to the list
- An invalid email id sends the user back to the list

The period, provider, status and page size selectors reload the page with the right query string, and the pagination keeps the filters.
