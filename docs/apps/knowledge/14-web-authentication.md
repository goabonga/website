# Web authentication

Browsers authenticate through server-rendered pages under `/auth`, served by the
internal sub-application (tag `Auth`, visible in `/internal/docs`). The pages
sign visitors up and in against the platform authentication service and let
them manage their account. Session state lives in cookies; the bearer-token
flow of the API is described in [OAuth2 authentication](02-authentication.md).

## Two ways to sign in

1. **Authorization code with PKCE** (`GET /auth/login`, `GET /auth/callback`).
   `login` generates a `state` and a PKCE verifier, stores them with the return
   URL in short-lived cookies (`oauth_state`, `oauth_code_verifier`,
   `oauth_redirect`, 10 minutes) and redirects to
   `<OAUTH2_ISSUER>/oauth2/authorize` with the public client
   `OAUTH2_FRONTEND_CLIENT_ID`, scopes `openid profile email offline_access` and
   the `S256` challenge. `callback` checks the state, exchanges the code at
   `<issuer>/oauth2/token`, reads `<issuer>/userinfo` and creates the session.
   Errors are shown on the `auth/error.html` page with an explicit status code
   (`400` for protocol problems, `500` when OAuth2 is not configured or the
   issuer cannot be reached).
2. **Forms on this site** (`/auth/signup`, `/auth/verify`, `/auth/signin`).
   The password never goes to the browser's identity provider: the service calls
   the authentication service API on the visitor's behalf (`AuthAPIClient`,
   confidential client `OAUTH2_CLIENT_ID`/`OAUTH2_CLIENT_SECRET`, password grant).

On the first sign-in of a user without any workspace, the callback creates a
personal workspace (a free `Tenant` named `<name>'s Workspace` with the user as
owner member); the signin form creates the workspace chosen during signup, or
redirects to `/auth/create-workspace` when none was named.

## Session cookies

| Cookie | Content | Lifetime |
| --- | --- | --- |
| `access_token` | Access token (HTTP-only). | Token `expires_in`. |
| `refresh_token` | Refresh token (HTTP-only). | 30 days, 90 days with "remember me". |
| `active_tenant_id` | Id of the active workspace (HTTP-only). | 1 year. |
| `user_info` | `{id, email, name}` JSON, readable by JavaScript. | Token `expires_in`. |
| `knowledge_mfa_signin_challenge` | Signed pending second-factor signin. | 5 minutes. |

Cookies are `Secure` unless `COOKIE_SECURE=false`, `SameSite=Lax`, and scoped to
`COOKIE_DOMAIN` when it is set. `GET /auth/logout` clears them and redirects to
`?redirect=` (default `/`); `POST /auth/refresh` renews the access token from the
refresh cookie.

## Routes

| Route | Purpose |
| --- | --- |
| `GET /auth/login`, `GET /auth/callback`, `GET /auth/logout`, `POST /auth/refresh` | PKCE login, logout and token refresh. |
| `GET`/`POST /auth/signup` | Registration form (email, password and confirmation, nickname, first and last name, workspace name, personal or enterprise plan with company details). Mismatched passwords or a missing company name for enterprise are `400`; an already registered email redirects to signin. |
| `GET`/`POST /auth/verify`, `POST /auth/verify/resend` | Email verification with the emailed code. |
| `GET`/`POST /auth/signin` | Email and password signin, with optional authenticator or backup code, or an emailed code. |
| `GET`/`POST /auth/create-workspace` | First workspace for an authenticated user who has none. |
| `GET`/`POST /auth/forgot-password`, `GET`/`POST /auth/reset-password` | Password reset. The forgot form always answers with the same message so that it cannot be used to discover accounts. |
| `GET`/`POST /auth/account` | Profile (nickname, names, picture, website, phone, timezone, locale). |
| `GET /auth/account/security`, `POST /auth/account/security/{setup,verify,disable,regenerate-codes}`, `POST /auth/account/password` | Two-factor authentication (TOTP with backup codes) and password change. |

The `AuthAPIClient` methods map to the authentication service endpoints
`/auth/register/api`, `/auth/verify-email/api`, `/auth/resend-verification/api`,
`/auth/forgot-password/api`, `/auth/reset-password/api`, `/auth/login`,
`/oauth2/token`, `/userinfo`, `/api/me/profile`, `/api/me/password` and
`/api/me/mfa/*`. Failures are raised as `AuthAPIError` and rendered on the page.

### Second-factor signin

When the authentication service reports that a second factor is required, the
signin page asks for the authenticator or backup code and sets the signed
`knowledge_mfa_signin_challenge` cookie so that the second submission does not
need the password again. The cookie is signed (HMAC-SHA256, key derived from
the OAuth2 client secret) but not encrypted, and it carries the credentials the
first step received; it is limited to 5 minutes and cleared on success.

## Web authentication in the API layer

`knowledge.auth.dependencies` gains the cookie-based helpers used by every web
page: `get_current_user_or_redirect` (validate the cookie token like the API does,
with token exchange, or redirect to `/auth/login?redirect=<path>`, the path and the whole
query string of the page being asked for, URL-encoded),
`get_web_auth_context` (user, active workspace taken from the cookie and
checked against the memberships, falling back to the first workspace),
`require_scope_or_redirect`, `require_resource_scopes_or_redirect` and
`require_tenant_admin` (which render `errors/403.html`). `WebAuthContext`
(in `knowledge.auth.models`) exposes the user, the workspace, the membership and
the role helpers (`is_tenant_admin`, `can_manage_members`, ...).

## Templates

`knowledge/templates/base.html` is the shared layout; the `auth/` templates
(`signin`, `signup`, `verify`, `forgot_password`, `reset_password`,
`create_workspace`, `error`, and the `account*` pages) and `errors/403.html` are
rendered with Jinja2. The sidebar only lists pages that exist: it links to the
account pages, and each of the following features adds the link of its own pages.
The "API Docs" link only appears when `DOCS_ENABLED` is true, the documentation
being served only then.

## Settings

| Variable | Default | Description |
| --- | --- | --- |
| `OAUTH2_FRONTEND_CLIENT_ID` | empty | Public PKCE client for the browser login. |
| `APP_BASE_URL` | empty | Public base URL, used to build the callback URL (the request URL is used when empty). |
| `COOKIE_SECURE` | `true` | Mark cookies `Secure`; set to `false` for local development over HTTP. |
| `COOKIE_DOMAIN` | empty | Cookie domain; empty means the current host only. |

The issuer and the confidential client are the ones of the API authentication.
`python-multipart` (form parsing) and `jinja2` are runtime dependencies of this
feature.

## Tests

pytest:

- `test_auth_routes.py`: every route of `/auth` with mocked authentication
  client, database and HTTP calls (login, callback outcomes, logout, refresh,
  signup, verification, signin including MFA, workspace creation, password
  reset, profile, security and password change).
- `unit/test_auth_api_service.py`: each `AuthAPIClient` call, its payloads and
  its error mapping.
- `unit/test_auth_dependencies.py` and `unit/test_auth_models.py`: the
  cookie-based dependencies (including the login redirect that keeps the query
  string of the page) and `WebAuthContext`.
- `test_auth_routes.py` also checks the titles of the account pages and that the
  "API Docs" link of the sidebar follows `DOCS_ENABLED`.

behave (`features/web_authentication.feature`): templates and routes are real;
the authentication service client, the OAuth2 endpoints and the database are
in-memory fakes.

- The login page redirects to the authorization endpoint with PKCE
- The login page reports a missing OAuth2 configuration
- The callback rejects a state that does not match
- The first login creates a personal workspace and signs the user in
- Logging out clears the session cookies
- The signup form is displayed
- Signup requires matching passwords
- A successful signup leads to email verification
- Signing up with an existing email leads to signin
- Email verification accepts the right code
- Email verification rejects a wrong code
- Signin with wrong credentials shows an error
- Signin without a workspace asks the user to create one
- Signin after signup creates the chosen workspace
- Signin asks for a second factor when the account requires one
- Forgotten passwords never reveal whether the account exists
- Resetting a password needs a token
- A password reset leads back to signin
- Account pages require a signed-in user
- A signed-in user sees their profile
- A signed-in user updates their profile

browser (`features/browser/web_authentication.feature`, tag `@browser`): the same
pages driven in a real Chromium by Playwright. The application is served on a local
port, the sign-in goes through the fake OpenID provider of `e2e-support`, the
database is a SQLite file, and the authentication service behind the sign-up and
password pages is a stand-in that registers its users in the provider. The scenarios
read the verification codes and reset links like a user reads a mailbox, and every
link of the sidebar is followed to check that it leads to a page.

- A visitor signs in through the identity provider with PKCE
- A wrong password at the identity provider is refused
- A protected page sends the visitor to sign in and brings them back
- The return address of a protected page keeps its query string
- Signing out clears the session
- A token revoked at the provider sends the user back to sign in
- A visitor signs up, verifies the email and signs in
- Signing up requires matching passwords
- Signing up requires a password that meets the rules
- A wrong verification code is refused
- The sign-in page refuses a wrong password
- The sign-in page signs a user with a password in
- The sign-in page offers the identity provider
- A forgotten password is reset with the link that was sent
- A reset link without a token is refused
- The account pages require a signed-in user
- A signed-in user updates their profile
- The security page shows the two-factor status
- The sidebar of the account pages only leads to pages that exist
