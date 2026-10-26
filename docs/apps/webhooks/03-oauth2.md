# OAuth2 client credentials

Webhook handlers forward events to internal services (mailler, billing, ...).
This feature gives the gateway the machine-to-machine credentials it needs
to call them, so that those services can enforce scope-based access control
on their webhook endpoints. It is the building block used by every provider
feature that follows.

## What it does

`webhooks.auth` provides:

- `OAuth2ClientCredentials`, which acquires an access token with the OAuth2
  `client_credentials` grant (form-encoded POST to `OAUTH2_TOKEN_URL`,
  requesting the scope `mailler:webhooks billing:webhooks`, 10 second
  timeout) and caches it in memory. The token is refreshed 30 seconds before
  it expires. `expires_in` defaults to 3600 seconds when the server omits
  it.
- `get_authorization_header(static_token="")`, which returns the value of the
  `Authorization` header to send downstream:
    1. `Bearer <access token>` when OAuth2 is configured and a token could be
       obtained,
    2. otherwise `Bearer <static token>` when a static token is given,
    3. otherwise `None` (no header is sent).

If the token endpoint answers with an error status or fails, a previously
cached token that has not expired yet is reused (with a warning); otherwise
the static token is the fallback. Failures are logged and never raised.

Not every service relies on the token: billing authenticates the Stripe
webhook with the Stripe signature and ignores the bearer token unless its
`STRIPE_WEBHOOK_REQUIRED_SCOPE` is set ([Stripe webhook proxy](06-stripe.md)).

OAuth2 is considered configured only when `OAUTH2_TOKEN_URL`,
`OAUTH2_CLIENT_ID` and `OAUTH2_CLIENT_SECRET` are all set.

## Settings

| Variable | Default | Description |
| --- | --- | --- |
| `OAUTH2_TOKEN_URL` | empty | Token endpoint of the authorization server |
| `OAUTH2_CLIENT_ID` | empty | OAuth2 client identifier |
| `OAUTH2_CLIENT_SECRET` | empty | OAuth2 client secret |

Secrets can also be provided as systemd credentials.
`webhooks.config.get_credential(name, default)` reads the file `name` in the
directory pointed to by `CREDENTIALS_DIRECTORY` when it exists (content
stripped), then falls back to the environment variable and finally to the
default. The module-level `settings` object loads `OAUTH2_CLIENT_SECRET`
through it; the provider features do the same for their own secrets.

## Data model

None. The token is cached in process memory only.

## How it is tested

Pytest:

- `test_auth.py` - `is_configured` for every missing setting, cached token,
  successful acquisition, default `expires_in`, non-200 answers and
  exceptions with and without a stale token, and the header selection
  order in `get_authorization_header`.
- `test_config.py` - OAuth2 defaults and overrides, `get_credential`
  (credentials directory, environment, default, stripping) and loading of
  the client secret from `CREDENTIALS_DIRECTORY`.

Behave (`apps/webhooks/features/oauth2.feature`). The token endpoint is an
in-process fake (`httpx.MockTransport`), so no network is involved:

- Static token is used when OAuth2 is not configured
- No header is built without any credentials
- Access token is acquired from the token endpoint
- Access token is cached between calls
- Static token is the fallback when the token endpoint fails

```bash
uv run --package webhooks pytest apps/webhooks
uv run --package webhooks behave apps/webhooks/features
```
