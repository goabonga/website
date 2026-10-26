# Sessions and logout

A signed-in browser is identified by an opaque session cookie. This feature
adds the session service and repository, the middleware that extends active
sessions, the `AuthService` that checks a password, and the logout
endpoints. Creating a session after a successful sign-in is done by the
login feature that follows.

## What it does

- `SessionService.create_session` generates a random session token and a
  CSRF token, stores only their SHA-256 hashes in the `sessions` table
  together with the client IP address and user agent, and sets the expiry to
  `SESSION_EXPIRY_DAYS` from now. The clear tokens are returned once, to be
  set as cookies.
- Lookups (`get_session_by_token`, `get_user_by_session_token`) only return
  sessions that are neither revoked nor expired. `verify_csrf_token` checks a
  CSRF token against the hash of its session.
- `revoke_session` revokes one session (`revoked_at`), `revoke_all_user_sessions`
  revokes all the active sessions of a user, optionally keeping the current
  one. The service also lists and counts sessions and revokes them on behalf
  of an administrator, for the management features that follow.
- `AuthService.authenticate` returns the user for an e-mail address and a
  password, and `None` unless the address is verified, the account is active
  and the password matches the current Argon2id hash.
- `SlidingSessionMiddleware` implements a sliding expiration. After each
  request that carries a session cookie it checks whether the session is in
  the last 10% of its lifetime; if so it extends the session by a full
  lifetime in the database and re-issues the cookie with the new `Max-Age`
  (`HttpOnly`, `SameSite=Lax`, `Secure` unless `SESSION_COOKIE_SECURE` is
  off). Failures are logged and never break the request. `auth.main`
  installs it for every request.
- The cookie name comes from `get_session_cookie_name()` of the tenancy
  feature, so each tenant has its own cookie.
- The logout endpoints revoke the session, dispatch the `logout` and
  `session.revoked` webhook events and delete the session and CSRF cookies.
  The form variants redirect (303) to `/auth/login`; the `/api` variants
  answer in JSON and return 401 when the cookie is missing or invalid.

## Endpoints

| Method | Path | Handler | Summary |
| --- | --- | --- | --- |
| POST | `/auth/logout` | `logout_submit` | Terminate the current session and redirect to the login page. |
| POST | `/auth/logout/api` | `logout_api` | Terminate the current session and return a JSON confirmation. |
| POST | `/auth/logout/all` | `logout_all_submit` | Revoke every active session for the user and redirect to the login page. |
| POST | `/auth/logout/all/api` | `logout_all_api` | Revoke every active session for the user and return a JSON confirmation. |

## Settings

| Variable | Default | Description |
| --- | --- | --- |
| `SESSION_EXPIRY_DAYS` | `7` | Session validity in days |
| `SESSION_COOKIE_SECURE` | `True` | Secure cookie (HTTPS only) |

The session cookie name itself (`SESSION_COOKIE_NAME`) was introduced with the
tenancy feature.

## Data model

Uses the `sessions` table: hashed session and CSRF tokens, `ip_address`,
`user_agent`, `expires_at`, `revoked_at` and the optional `tenant_id` of the
tenant the session belongs to.

## Tests

- pytest: 5 new test modules and 1 existing modules extended.
  New modules: `tests/test_auth_service.py`, `tests/test_middleware_session.py`, `tests/test_routes_auth_logout.py`, `tests/test_session_repository.py`, `tests/test_session_service.py`.
  Extended: `tests/test_api_deps.py`.
- behave: `features/sessions.feature` with the scenarios *A session token is stored hashed and resolves to its user*, *An expired session is not valid*, *The CSRF token is bound to its session*, *Signing out revokes the session and clears the cookies*, *Signing out through the form redirects to the login page*, *Signing out without a session is refused by the API*, *Signing out everywhere revokes every session of the user*, *A session close to its end is extended on use*, *A session with plenty of time left is left alone*, *Only verified, active users with the right password authenticate*.

The behave scenarios create users and sessions in the in-memory database and
call the logout endpoints and the middleware through the application, with
the session cookie set on the test client.

### Browser scenarios

`features/browser/sessions.feature` is tagged `@browser`: its 7 scenarios drive the
application in Chromium (see [browser tests](../../testing/index.md)).

- The session cookie is hidden from the scripts of the page
- A session close to its end is extended while the user browses
- A session far from its end is left alone
- Signing out through the API removes the cookie from the browser
- Signing out through a form removes the cookie and returns to the login page
- Signing out everywhere revokes every session of the user
- A request without a session cannot sign out

The feature has no page of its own (the login and settings pages come with later features), so the scenarios hand the cookie of a session to the browser and check what Chromium does with it: the cookie is hidden from scripts, extended while the user browses and removed by the logout endpoints, called from the page with `fetch` or with a form.
