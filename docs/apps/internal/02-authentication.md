# OAuth2 authentication

Every page of the dashboard is protected by OAuth2 / OIDC. Browsers log in with
the authorization code flow and PKCE through a public client; the server then
validates the resulting access token on every request, and asks the authorization
server for the exact scopes a page needs through RFC 8693 token exchange. API
callers can send the same token as a bearer header.

## What it adds

| Module | Role |
| --- | --- |
| `internal/auth/__init__.py` | Authentication module with JWT validation and scope-based authorization. |
| `internal/auth/jwt.py` | JWT validation with JWKS support and token introspection. |
| `internal/auth/models.py` | Authentication models. |
| `internal/auth/dependencies.py` | FastAPI authentication dependencies with scope-based authorization. |
| `internal/services/__init__.py` | Application services. |
| `internal/services/token_exchange.py` | Token Exchange client (RFC 8693) with Redis caching. |
| `internal/routes/__init__.py` | Routes package for internal application. |
| `internal/routes/auth.py` | OAuth2 authentication routes for HTML pages. |

It also ships 2 Jinja2 template(s) under `internal/templates/` (packaged with the wheel).

## Endpoints

| Method | Path | Required scope | Description |
| --- | --- | --- | --- |
| GET | /auth/login | none | Redirect to OAuth2 authorization endpoint. |
| GET | /auth/callback | none | OAuth2 callback - exchange authorization code for tokens. |
| GET | /auth/logout | none | Logout - clear authentication cookies. |
| GET | /auth/refresh | none | Refresh access token using refresh token. |

These routes need no scope: they are the authentication flow itself.

## Login flow

1. `GET /auth/login` generates a `state` and a PKCE verifier, stores them (and the
   post-login `redirect`) in short-lived (10 minutes) HTTP-only cookies and
   redirects to `<issuer>/oauth2/authorize` with the public frontend client and
   the scopes `openid profile email offline_access`.
2. `GET /auth/callback` checks the `state` cookie, exchanges the code (with the PKCE
   verifier, no client secret) at `<issuer>/oauth2/token`, fetches the user
   profile from the userinfo endpoint and sets three cookies: `access_token`
   and `refresh_token` (HTTP-only) and `user_info` (readable by scripts, holds
   name, email and picture). Provider errors, a missing code, a state mismatch or a
   failed token exchange render `auth/error.html`; an error that mentions PKCE
   or a missing verifier cookie restarts the login instead, sending the page asked for to
   `/auth/login` URL-encoded so that its whole query string comes back.
3. `GET /auth/refresh` trades the refresh token for a new pair. `GET /auth/logout`
   deletes every authentication cookie and redirects to `redirect`
   (default `/auth/login`).

## Token validation

`internal.auth.jwt.JWTValidator` fetches the issuer's JWKS (cached in memory),
verifies the signature (`RS256` or `ES256`) and the issuer, and then runs an RFC 7662
token introspection to detect revoked tokens. The introspection result is cached in
Redis for `TOKEN_INTROSPECTION_CACHE_TTL` seconds under a key derived from a hash of the
token (the token itself is never stored). Without a Redis URL the check simply
runs every time.

`internal.auth.dependencies` exposes the FastAPI dependencies:

- `get_current_user` - bearer header first, then the `access_token` cookie;
  answers `401` for a missing, invalid or revoked token and `503` when no issuer is configured.
- `get_current_user_or_redirect` - for HTML pages: redirects to
  `/auth/login?redirect=<current path>` instead of answering `401`, and when only a
  refresh token is present it silently refreshes. Refreshed tokens are handed to
  `TokenRefreshMiddleware`, which writes the new cookies on the response.
- `require_scope`, `require_scopes`, `require_any_scope` - API style checks that answer `403`.
- `require_scope_or_redirect(scope)` and
  `require_resource_scopes_or_redirect(resource, required_scope=None, extra_scopes=None)` -
  page style checks. The second one asks for `<resource>:read`, `:write` and
  `:delete` in a single exchange so templates can show or hide edit and delete
  buttons; the minimum needed to open the page is `<resource>:read` unless
  `required_scope` says otherwise. A missing scope renders `errors/403.html`.

## Scopes and token exchange

`internal.services.token_exchange.TokenExchangeClient` implements RFC 8693 with the
confidential client (`OAUTH2_CLIENT_ID` / `OAUTH2_CLIENT_SECRET`). Granted scopes are
cached in Redis for `OAUTH2_CLIENT_CACHE_TTL` seconds. When the client is not configured the
dependencies fall back to the scopes carried by the JWT itself. Scopes returned by the
exchange are merged with the token's own scopes so that a wildcard is never lost. The authorization server
wraps its OAuth2 errors in FastAPI's `detail` (`{"detail": {"error": ..., "error_description": ...}}`):
the client reads that object (and a top-level error), so `insufficient_scope` is told apart from other failures and
the 403 page names the missing scope.

Every HTML page renders the admin sidebar, whose links depend on the user's scopes, and
the access token only carries the OIDC scopes. `require_scope_or_redirect` and
`require_resource_scopes_or_redirect` therefore always add `SIDEBAR_SCOPES`
(`vpn:admin` and `billing:read`) to the scopes they request, so the sidebar of every page
(read pages, write forms, the VPN, billing and team pages) shows the same links.
These scopes are never required: the exchange may grant only them, in which case
`require_scope_or_redirect` still answers `403` because the scope the page needs is missing.

`internal.auth.models.User.has_scope` understands wildcards: `*` grants everything,
`<resource>:*` grants every action on a resource, and `internal:*` grants the
`namespaces`, `prompts`, `knowledge` and `conversations` resources.

## Swagger UI

When `OAUTH2_ISSUER` and `OAUTH2_SWAGGER_CLIENT_ID` are both set, the generated
`/docs` page (if enabled) is pre-configured for the authorization code flow with PKCE
using the public Swagger client.

## Settings

Read from environment variables (or a `.env` file) by `internal.config.Settings`.

| Variable | Default | Notes |
| --- | --- | --- |
| `REDIS_URL` | `'redis://localhost:6379/0'` | Redis |
| `REDIS_KEY_PREFIX` | `'internal'` | Redis |
| `APP_BASE_URL` | a placeholder URL | Application URL (for OAuth2 redirect URI) |
| `COOKIE_SECURE` | `True` | Set to False for local development without HTTPS |
| `OAUTH2_ISSUER` | `''` | OIDC issuer URL (e.g., https://auth.example.com) |
| `OAUTH2_SWAGGER_CLIENT_ID` | `''` | Public PKCE client for Swagger UI |
| `OAUTH2_FRONTEND_CLIENT_ID` | `''` | Public PKCE client for HTML pages |
| `OAUTH2_CLIENT_ID` | `''` | Confidential client for introspection/token exchange |
| `OAUTH2_CLIENT_SECRET` | `''` | Client secret for introspection/token exchange |
| `OAUTH2_CLIENT_CACHE_TTL` | `300` | Cache exchanged tokens for 5 minutes |
| `TOKEN_INTROSPECTION_CACHE_TTL` | `60` | seconds |

Three OAuth2 clients are involved: a public PKCE client for Swagger
(`OAUTH2_SWAGGER_CLIENT_ID`), a public PKCE client for the browser login
(`OAUTH2_FRONTEND_CLIENT_ID`) and a confidential client for introspection and
token exchange (`OAUTH2_CLIENT_ID` + `OAUTH2_CLIENT_SECRET`). The client secret is
read through `get_credential`, so it can come from a systemd credential.
`COOKIE_SECURE` must be `false` for plain-HTTP local development. `REDIS_KEY_PREFIX`
is declared in the settings but no code reads it yet.

## Tests

pytest:

- `tests/test_jwt.py`
- `tests/test_dependencies.py`
- `tests/test_models.py`
- `tests/routes/test_auth.py`
- `tests/routes/test_init.py`
- `tests/services/test_token_exchange.py`

The tests cover the JWT validator (JWKS lookup, signature and issuer checks, introspection and its cache), every dependency including the refresh and 403 paths, the sidebar scopes added to every exchange (and the 403 when only they are granted), the token exchange client, the four auth routes and `User` scope matching. The token exchange client is also tested with the error shape of the authorization server (the OAuth2 error inside `detail`), and the callback with a page whose query string must survive the redirect to the login.

Behave scenarios, run in-process with `uv run --package internal behave apps/internal/features` (`features/auth.feature`):

- Login redirects to OAuth2 authorize URL
- Login preserves redirect parameter
- Callback with valid code and state sets cookies and redirects
- Callback with OAuth2 error shows error page
- Callback with PKCE error redirects to login
- Callback with missing code shows error
- Callback with state mismatch shows error
- Callback with expired state cookie redirects to login
- Callback with missing code verifier redirects to login
- Callback with token exchange failure shows error
- Logout clears cookies and redirects
- Logout with custom redirect
- Refresh with valid refresh token redirects with new cookies
- Refresh without refresh token returns 401
- Refresh with failed token refresh redirects to login

The OAuth2 scenarios mock `httpx.AsyncClient` instead of the standard authentication mocks, because the routes under test are the authentication flow; every other feature authenticates through the mocked validator and token exchange set up in `features/environment.py`.

Browser scenarios, run in Chromium against the application served on a local socket (`features/browser/auth.feature`, `uv run --package internal --group dev behave apps/internal/features -t @browser`):

- Signing in goes through the provider and comes back to the page asked for
- The login sets the session cookies and clears the temporary ones
- The token cookies are not readable by scripts
- The login cookies are set while the browser is at the provider
- A wrong password keeps the user at the provider
- A user who denies the consent is told so
- A user who allows the consent is signed in
- The callback shows the error the provider reports and offers to try again
- The callback without a code is an invalid request
- The callback refuses a state that is not the one of the login
- The callback sends a user whose login expired back to the provider
- The callback reports an authorization code the provider refuses
- Refreshing the token rotates the cookies
- Refreshing without a session is refused
- A refresh token the provider no longer knows sends the user to log in again
- Signing out clears the session cookies
- Signing out does not end the session at the provider

The login runs for real: the application and the fake OpenID provider of `libs/e2e-support` listen on local sockets, Chromium follows the redirects, signs in at the provider's login page and comes back through `/auth/callback`. The scenarios check the PKCE exchange the provider received, the cookies set (HTTP-only access and refresh tokens, a `user_info` cookie readable by scripts, no temporary cookie left), the error page of every refused callback and the refresh and logout routes. Logging out only clears the cookies of the application: the session of the provider survives, so the next login is silent.
