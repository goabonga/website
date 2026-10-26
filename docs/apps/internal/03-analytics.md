# Analytics dashboards

Operators can browse the platform's web analytics from the dashboard. The
application owns no analytics data: every figure comes from the analytics service
over HTTP and is rendered into Jinja2 pages. This feature also introduces the shared
page layout, `admin/base.html`, with a navigation sidebar that grows by one entry per
feature (only the entries of the features present are rendered).

## What it adds

| Module | Role |
| --- | --- |
| `internal/services/analytics_client.py` | HTTP client for analytics API (ua.goabonga.com). |
| `internal/services/analytics_client_sync.py` | Synchronous HTTP client for analytics API (for Celery tasks). |
| `internal/routes/analytics.py` | Analytics dashboard routes for HTML pages. |

It also ships 6 Jinja2 template(s) under `internal/templates/` (packaged with the wheel).

## Endpoints

| Method | Path | Required scope | Description |
| --- | --- | --- | --- |
| GET | /analytics | `analytics:read` | Analytics overview dashboard. |
| GET | /analytics/campaigns | `analytics:read` | List all marketing campaigns. |
| GET | /analytics/campaigns/{campaign_id} | `analytics:read` | View detailed campaign statistics. |
| POST | /analytics/campaigns/{campaign_id}/delete | `analytics:write` | Delete an analytics campaign. |
| POST | /analytics/campaigns/bulk-delete | `analytics:write` | Delete multiple analytics campaigns. |
| GET | /analytics/ips | `analytics:read` | List IP addresses with their statistics. |
| GET | /analytics/ips/{ip_address:path} | `analytics:read` | View detailed statistics for a specific IP address. |
| POST | /analytics/reset | `analytics:delete` | Reset all analytics data. Requires analytics:delete scope (super_admin only). |

The dashboard and list pages ask the authorization server for all of `analytics:read`,
`:write`, `:delete` plus `vpn:admin` and `billing:read` in a single exchange, so the page can
show the right buttons and the navigation can show the VPN and billing links.

## Pages

- **Dashboard** (`/analytics?days=30`): overview totals, a daily series, and the top
  countries, devices, browsers, referrers, pages, events and IP addresses for the last
  1 to 365 days.
- **Campaigns** (`/analytics/campaigns`, `/analytics/campaigns/{id}`): tracked
  campaigns with their pixels. Campaigns can be deleted one by one or in bulk.
- **IP addresses** (`/analytics/ips`, `/analytics/ips/{address}`): visits grouped by IP
  with a per-address detail page.
- **Reset** (`POST /analytics/reset`): wipes all analytics data on the remote
  service. It needs `analytics:delete`, which in practice only a super administrator holds.

## Analytics client

`internal.services.analytics_client.AnalyticsClient` (instance `analytics_client`) is an
async `httpx` client. It authenticates with the OAuth2 client-credentials grant against
`<issuer>/oauth2/token`, asks for the scope an operation needs (`analytics:read` by
default) and caches one token per scope until 30 seconds before it expires. Statistics
getters return Pydantic models; on any error they log the exception and return `None` or
an empty list, so a dashboard section degrades to "no data" instead of failing the page.
Write operations (create or delete campaigns and pixels, reset) return a success flag or `None`.

`internal.services.analytics_client_sync.SyncAnalyticsClient` is a synchronous variant
of the campaign and pixel calls, meant for Celery tasks; no task of this application uses
it yet.

## Settings

Read from environment variables (or a `.env` file) by `internal.config.Settings`.

| Variable | Default | Notes |
| --- | --- | --- |
| `ANALYTICS_API_URL` | a placeholder URL | Analytics API |

`ANALYTICS_API_URL` is the base URL of the analytics service. The access token is requested with `OAUTH2_CLIENT_ID` / `OAUTH2_CLIENT_SECRET` from the authentication feature.

## Tests

pytest:

- `tests/routes/test_analytics.py`
- `tests/services/test_analytics_client.py`
- `tests/services/test_analytics_client_sync.py`
- `tests/sidebar.py` (shared helper)
- `tests/routes/test_analytics_sidebar.py`
- `tests/test_templates.py` (all the templates of the application)

The tests cover every route handler (including authorization redirects and the bulk delete and reset paths) and both HTTP clients (token caching, error handling, every endpoint wrapper).

`tests/routes/test_analytics_sidebar.py` opens every page of this feature through the application with its real templates (throw-away SQLite database, mocked service clients) and, for each scope combination, checks the sidebar: exactly the links the scopes permit, a single active link and the signed-in user. `tests/sidebar.py` holds the helpers: a fake token exchange that, like the authorization server, grants the requested scopes the user holds (the access token itself only carries the OIDC scopes), the registry of sidebar sections and pages, and a test checking the registry against `admin/base.html`. Forbidden pages are standalone and show no sidebar.

`tests/test_templates.py` reads every template of the application and checks two things that a browser silently repairs: no `<form>` is nested in another form (the browser would drop the inner one and its button would submit the outer form) and an inline event handler only interpolates identifiers, counters or values passed through `tojson` (a quote in a name would end the JavaScript string).

Behave scenarios, run in-process with `uv run --package internal behave apps/internal/features` (`features/analytics.feature`):

- View analytics dashboard
- View analytics dashboard unauthenticated
- View analytics dashboard with custom days parameter
- List campaigns
- View campaign detail when found
- View campaign detail when not found
- Delete campaign successfully
- Delete campaign failure
- Bulk delete campaigns
- Bulk delete with invalid UUIDs
- View IP stats list
- View IP detail when found
- View IP detail when not found
- Reset analytics with delete scope
- Reset analytics failure
- Sidebar on the analytics dashboard
- Sidebar on the campaigns list
- Sidebar on the campaign detail
- Sidebar on the IP addresses list
- Sidebar on the IP address detail

The sidebar scenarios authenticate through a token exchange that grants only the requested scopes (`I am authenticated with only the scopes "..." granted by token exchange`), then assert the links and the active section on the rendered page (`features/steps/sidebar_steps.py`).

The analytics client is replaced by an `AsyncMock`; scenarios check redirects for anonymous users, 403 pages for missing scopes, and the success and error redirects of the delete and reset actions.

Browser scenarios, run in Chromium against the application served on a local socket (`features/browser/analytics.feature`, `uv run --package internal --group dev behave apps/internal/features -t @browser`):

- An anonymous visitor is sent to the provider and lands on the page asked for
- The query of the page asked for survives the login
- The sidebar highlights the analytics section on every page of the feature
- The sidebar links lead to the sections
- Signing out from the sidebar ends the session
- The dashboard shows the statistics of the period
- Changing the period reloads the dashboard
- The dashboard links to the IP addresses and the campaigns
- A user without the analytics scope gets the access denied page
- Resetting the analytics asks for a confirmation and reports the result
- A failed reset is reported as an error
- A user who cannot delete cannot reset
- The campaign list links to the campaign
- Deleting a campaign from its page confirms and reports success
- A campaign that cannot be deleted is reported on its page
- A missing campaign sends the user back to the list
- Selected campaigns are deleted in bulk
- The list can include the inactive campaigns
- The IP list links to the detail of an address
- The number of addresses and the period are filters of the list
- An unknown address sends the user back to the list

A visitor who is not signed in is sent to the provider and comes back to the page asked for with its whole query string. The sidebar is read in the browser: the highlighted section, the links, the signed in user and the link that leads to the dashboard. The period and filter selectors, the confirmations of the delete and reset buttons and the bulk selection of the campaigns run their JavaScript. The analytics client is replaced by an `AsyncMock`, like in the other scenarios.
