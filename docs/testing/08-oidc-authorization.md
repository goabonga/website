# Authorization endpoint

`GET /oauth2/authorize` of the [fake provider](07-fake-openid-provider.md)
starts the authorization code flow. It runs the checks of the auth
application, in the same order and with the same error codes, so an
application that builds its login URL wrongly fails here as it would in
production.

## Request validation

| Check | Outcome |
| --- | --- |
| `response_type` or `redirect_uri` missing | Error page, `invalid_request` |
| `response_type` is not `code` | Error page, `unsupported_response_type` |
| `redirect_uri` is not https, http on localhost or a custom scheme | Error page, `invalid_request` (`Invalid redirect_uri`) |
| Unknown or inactive `client_id` | Error page, `unauthorized_client` |
| `redirect_uri` not registered for the client | Error page, `invalid_request` |
| A requested scope the client may not use | Redirect, `invalid_scope` |
| Client requires PKCE and `code_challenge` is missing, malformed or the method unsupported | Redirect, `invalid_request` |

Problems that make the redirect URI untrustworthy are shown on an HTML error
page (status 400, containing the error code and its description) instead of
being redirected. The others redirect to the application with `error`,
`error_description` and the echoed `state`. The scope defaults to `openid`;
the PKCE method defaults to `S256` and `plain` is accepted. Registered
redirect URIs are exact, or patterns where `*` matches any characters.

## Logging the user in

The next step depends on the provider options and the request:

| Situation | Behavior |
| --- | --- |
| `auto_approve=True` | No page: the user named by `login_hint` (an email) or else the first configured user is logged in. Without any user, an error page |
| A session cookie from a previous login | Single sign-on: no page |
| Otherwise | The login page |
| `prompt=login` | The login page even with a session |
| `prompt=none` without a session | Redirect with `login_required` |

The **login page** (`<h1>Sign in</h1>`) has an Email field, a Password field
and a Sign in button, so the [generic steps](06-steps.md) fill it with `I
fill "Email" with ...`. The email is prefilled from `login_hint`. A wrong
email or password shows `<p role="alert">Invalid email or password.</p>`; a
user with no `password` accepts any. Submitting posts to
`/oauth2/authorize/login`, sets the `e2e_oidc_session` cookie (HttpOnly,
used for single sign-on) and continues.

With `require_consent=True` a **consent page** (`Authorize access`) follows
the login, listing the requested scopes with Allow and Deny buttons (posted
to `/oauth2/authorize/consent`). Deny redirects with `access_denied`.

`provider.end_sessions()` forgets every session so that the next
authorization asks for a login again.

## The code

Allowing the request redirects (302, or 303 after a form post) to the
`redirect_uri` with `code` and the echoed `state`. The code is random, valid
for `code_ttl` seconds and bound to the client, redirect URI, user, scopes,
PKCE challenge and nonce. It is redeemed once at the token endpoint, which
verifies the PKCE verifier. The PKCE helpers are in `e2e_support.oidc.pkce`
(`challenge_for(verifier, method)`, `verify(...)`, validity checks) and can
be used to build requests in tests.

Cookies are shared by every server on the same host name whatever the port.
The provider's cookie is named `e2e_oidc_session`; make sure the
application under test does not use that name.

## How it is tested

Pytest (`libs/e2e-support/tests/test_oidc_authorize.py`): auto-approve, the
`login_hint`, default scope and nonce; the login page, success, wrong
password, unknown email, passwordless user, single sign-on, `prompt=login`
and `prompt=none`; the consent page with allow and deny; every validation
rule above, split between error pages and redirects; the redirect-URI
format and pattern matching; PKCE helpers; and a real browser filling the
login page and landing on the redirect URI with a code (tagged `browser`).
