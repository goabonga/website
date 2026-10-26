# VPN session management

Operators with the `vpn:admin` scope can see who is connected to the VPN and cut a
session off. Like the other administration features it owns no data: the pages are
rendered from the VPN portal service's admin API. The navigation link to this page only
appears for users who hold `vpn:admin`.

## What it adds

| Module | Role |
| --- | --- |
| `internal/services/vpn_portal_client.py` | HTTP client for VPN Portal API. |
| `internal/routes/vpn.py` | VPN admin routes for HTML pages. |

It also ships 1 Jinja2 template(s) under `internal/templates/` (packaged with the wheel).

## Endpoints

| Method | Path | Required scope | Description |
| --- | --- | --- | --- |
| GET | /vpn/sessions | `vpn:admin` | List all VPN sessions with pagination. |
| POST | /vpn/sessions/{serial_number}/revoke | `vpn:admin` | Revoke a VPN session by certificate serial number. |

## Pages

- **Sessions** (`/vpn/sessions?page=1`): the active (not revoked, not expired) sessions,
  20 per page, with user name, device, assigned IP, connection and expiry times, granted
  scopes and routes. If the portal cannot be reached the page still renders, with an
  error banner and an empty list.
- **Revoke** (`POST /vpn/sessions/{serial_number}/revoke`): revokes the session of that
  certificate serial number and redirects back to the list with a `success` or
  `error` message. The serial number reaches the page's JavaScript through `tojson`, so a quote
  in it or in a user name cannot break the revoke buttons.

## VPN portal client

`internal.services.vpn_portal_client.VPNPortalClient` (instance `vpn_portal_client`)
authenticates with the OAuth2 client-credentials grant for the `vpn:admin` scope,
caches the token until shortly before it expires and calls two endpoints of the portal's
admin API: a paginated session listing and the revocation of a session by certificate
serial number. Both methods log failures and return `None` / `False` instead of raising.

## Settings

Read from environment variables (or a `.env` file) by `internal.config.Settings`.

| Variable | Default | Notes |
| --- | --- | --- |
| `VPN_PORTAL_API_URL` | a placeholder URL | VPN Portal API |

`VPN_PORTAL_API_URL` is the base URL of the VPN portal service.

## Tests

pytest:

- `tests/routes/test_vpn.py`
- `tests/services/test_vpn_portal_client.py`
- `tests/routes/test_vpn_sidebar.py`

The tests cover both route handlers (pagination maths, error banner, redirects) and the portal client (token handling, listing, revocation including the not-found case). The page is rendered for a session whose certificate serial number holds a quote to check the handlers of its buttons.

`tests/routes/test_vpn_sidebar.py` opens every page of this feature through the application with its real templates (throw-away SQLite database, mocked service clients) and, for each scope combination, checks the sidebar: exactly the links the scopes permit, a single active link and the signed-in user.

Behave scenarios, run in-process with `uv run --package internal behave apps/internal/features` (`features/vpn.feature`):

- View VPN sessions list
- View VPN sessions list unauthenticated
- View VPN sessions when service is unavailable
- Revoke VPN session successfully
- Revoke VPN session failure
- Revoke VPN session unauthenticated
- Sidebar on the VPN sessions list
- Sidebar on the VPN sessions list when the service is unavailable
- Sidebar gated links follow the scopes on the VPN sessions list

The portal client is replaced by an `AsyncMock`; the scenarios check the unauthenticated redirect and the success and failure redirects of revocation.

Browser scenarios, run in Chromium against the application served on a local socket (`features/browser/vpn.feature`, `uv run --package internal --group dev behave apps/internal/features -t @browser`):

- The sessions are listed for a user holding the VPN scope
- Only the holders of the VPN scope see the VPN link
- The VPN link is shown on the other pages to the holders of the VPN scope
- A user without the VPN scope gets the access denied page
- An anonymous visitor is sent to the provider and comes back to the sessions
- The list tells when the VPN service is unavailable
- Revoking a session asks to confirm and reports the success
- Cancelling the confirmation revokes nothing
- A session that cannot be revoked is reported
- A session of a user with an apostrophe in the name can be revoked

They check that the VPN link of the sidebar follows the `vpn:admin` scope on the pages of other sections, the inline revoke confirmation (shown, confirmed, cancelled) and that a session whose user name or certificate holds an apostrophe can still be revoked.
