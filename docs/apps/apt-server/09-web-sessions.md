# Web login sessions

Browser users sign in through the `auth` service with the OAuth2 Authorization
Code flow and PKCE, so no client secret reaches the browser. After login a
signed session cookie identifies them on the web pages and on the APIs that
accept an apt caller.

## Flow

1. `GET /login` creates a random `state` and a PKCE verifier, stores both in
   the signed `oauth_state` cookie (HTTP only, secure, `SameSite=Lax`, ten
   minutes) and redirects to `<issuer>/oauth2/authorize` with
   `response_type=code`, the client id, `scope=openid profile email`, the
   `state` and an `S256` code challenge. The client id is
   `OAUTH2_SWAGGER_CLIENT_ID`, falling back to `OAUTH2_CLIENT_ID`. The
   callback URL is built from the request, and forced to `https` when the
   proxy sends `X-Forwarded-Proto: https`. Answers 503 when `OAUTH2_ISSUER`
   is empty.
2. `GET /callback?code=&state=` checks the state cookie (400 when missing or
   when the state differs), exchanges the code at `<issuer>/oauth2/token`
   with the verifier (502 when the exchange fails or returns no access
   token), then reads `<issuer>/userinfo` (failures are logged and tolerated).
   The display name is the email, the name the nickname or name, and the avatar
   the profile picture, made absolute against the issuer, or a Gravatar
   identicon derived from the email. When the access token carries a `sub`, the
   profile is stored in the user cache. The answer redirects to `/` with the
   `apt_session` cookie and deletes `oauth_state`.
3. `GET /logout` deletes the session cookie and redirects to `/`.

All three routes are hidden from OpenAPI.

## The session cookie

`apt_server.services.session` signs the payload with HMAC-SHA256 using
`SESSION_SECRET` (the OAuth2 client secret when it is empty) and compares
digests in constant time. The cookie holds the access token, the display
name, the name, the avatar and the issue time, and is rejected when tampered,
malformed, without token or older than `SESSION_MAX_AGE`. It is HTTP only,
secure and `SameSite=Lax`.

The session is only a carrier for the access token. On every request
`resolve_caller` (see the APT endpoints page) falls back to the cookie when no
`Authorization` header is present, validates the stored token by
introspection and builds a `Caller` flagged `is_session`. A revoked or invalid
token degrades silently to an anonymous caller instead of failing with 401, so
a stale cookie never locks a visitor out of public pages. An
`Authorization` header always wins over the cookie.

## Settings

| Variable | Default | Description |
| --- | --- | --- |
| `SESSION_SECRET` | empty | Signs the cookies; also read from systemd credentials |
| `SESSION_COOKIE_NAME` | `apt_session` | Cookie name |
| `SESSION_MAX_AGE` | `86400` | Session lifetime (seconds) |

The OAuth2 client must be registered at the identity provider with the
`/callback` URL of the deployment as an allowed redirect URI.

## Tests

- pytest: `tests/test_session.py` (cookie round trip, tampering, expiry,
  secret fallback, PKCE, state cookie) and `tests/test_web_login.py` (login
  redirect parameters, proxy scheme, callback success and each error, user
  cache update, logout, and the cookie as a credential: precedence, revoked and
  forged sessions), with the identity provider replaced by
  `httpx.MockTransport`.
- behave: `features/web_sessions.feature` with the scenarios "Login redirects
  to the identity provider", "Completing the login creates a session", "A
  callback with a forged state is refused", "A callback without the state
  cookie is refused", "A failed code exchange is reported as a bad gateway",
  "The session cookie opens private components", "Without a session private
  components stay closed" and "Logging out clears the session cookie".
- browser: `features/browser/web_sessions.feature` (tag `@browser`, see
  [Browser testing](../../testing/index.md)) signs in at the fake OpenID
  provider of `libs/e2e-support` in Chromium, with the application and the
  provider on real sockets and the application pointed at the provider through
  its settings. The scenarios are "Signing in at the identity provider creates
  a session" (the callback sets the `apt_session` cookie, HTTP only and secure,
  and removes `oauth_state`), "The session opens the private components",
  "Without a session the private components stay closed", "Signing out closes
  the private components", "A wrong password keeps the visitor at the identity
  provider", "A callback that does not follow a login is refused", "A forged
  session cookie is ignored" and "A revoked token degrades the session to a
  visitor". The wiring is in `features/environment.py` and
  `features/browser_support.py`.
