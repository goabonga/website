# Identity provider federation

Organisations can let their members sign in with an external identity
provider (their corporate OpenID Connect provider, Google, Microsoft or
GitHub). This feature adds the federation service and the endpoints that
start the sign-in, receive the callback of the provider, provision or link the
local account and open a normal session.

## What it does

- Each `identity_providers` row belongs to a tenant and holds the provider
  type (`oidc`, `google`, `github`, `microsoft`; `saml` is declared in the model but no
  flow implements it), either a discovery URL or explicit authorization, token and
  userinfo endpoints, the client id, the client secret (stored encrypted with
  the `JWKS_ENCRYPTION_KEY`), the scopes, an optional attribute mapping, the
  allowed e-mail domains and the flags `is_active`, `auto_provision` and
  `allow_linking`, plus the button text and icon.
- `GET /federation/providers` lists the active providers of a tenant (from
  the tenant resolved by the middleware or the `tenant_slug` parameter) so that
  the login page can show one button per provider.
- `GET /federation/{idp_id}/authorize` needs a tenant context, builds the
  authorization URL (`response_type=code`, the scopes, a nonce and an S256 PKCE
  challenge) and redirects the browser to the provider. The data needed to
  complete the flow (tenant, provider, nonce, code verifier, the `redirect_uri`
  and `state` of the caller) travels in the `state` parameter, a base64 encoded
  JSON document.
- `GET /federation/callback` is the redirect URI registered at the provider. It
  decodes the state, exchanges the code for tokens at the token endpoint
  (with the client secret and the PKCE verifier), reads the claims from the ID
  token and the userinfo endpoint (GitHub has its own API), applies the
  attribute mapping and then calls `find_or_create_user`:
  - a known `(provider, subject)` pair signs the existing user in;
  - otherwise, if `auto_provision` is off, the sign-in is refused;
  - with `allow_linking`, a local account with the same e-mail address is
    linked to the identity;
  - otherwise a user is created with its profile and an address that is
    verified when the provider says so;
  - the user is enrolled in the tenant with its default role and a
    `member.added` webhook event is dispatched.
  It then opens a session, sets the session and CSRF cookies of the tenant
  and redirects to the `redirect_uri` given at the start (with the original
  `state` appended), or to `/auth/settings` (served by the settings pages
  feature). Provider errors and failures redirect to
  `/auth/login?error=federation_failed&message=...` (the reason is
  url-encoded); the login page shows a fixed message for the
  `federation_failed` code and does not echo the `message` parameter, which
  anybody can forge. A missing code or state, or an undecodable state,
  answers 400.
- Providers are created and edited through the organisation API and the admin
  and settings pages of the later features.

The ID token claims are read without verifying the signature, on the grounds
that the token comes straight from the provider's token endpoint over TLS.

## Endpoints

### `federation.providers`

| Method | Path | Handler | Summary |
| --- | --- | --- | --- |
| GET | `/federation/providers` | `list_providers` | List available identity providers for a tenant. |
| GET | `/federation/{idp_id}/authorize` | `initiate_federation` | Initiate federation flow with an external identity provider. |

### `federation.callback`

| Method | Path | Handler | Summary |
| --- | --- | --- | --- |
| GET | `/federation/callback` | `federation_callback` | Handle callback from external identity provider. |

## Settings

This feature adds no setting. It relies on `JWKS_ENCRYPTION_KEY` to decrypt the
client secrets.

## Data model

Uses `identity_providers` and `federated_identities` (the external subject,
e-mail and username, the raw claims, the link and last login dates), plus the
users, sessions and tenant members tables.

## Tests

- pytest: 3 new test modules.
  New modules: `tests/test_federation_repository.py`, `tests/test_federation_service.py`, `tests/test_routes_federation.py`.
- behave: `features/federation.feature` with the scenarios *The sign-in options of a tenant are listed*, *The visitor is sent to the identity provider with PKCE*, *A first sign-in provisions the user and opens a session*, *A returning user is recognised*, *A matching local account is linked*, *Providers can refuse to create accounts*, *An error reported by the identity provider is shown on the login page*, *Broken callbacks are refused*, *Unknown or inactive providers cannot be used*.

The behave scenarios put the application behind the tenant middleware and
replace the provider by an `httpx.MockTransport` that serves the discovery
document, the token endpoint and the userinfo endpoint, so the whole redirect,
callback, provisioning and linking sequence runs in process.

### Browser scenarios

`features/browser/federation.feature` is tagged `@browser`: its 5 scenarios drive the
application in Chromium (see [browser tests](../../testing/index.md)).

- A first sign-in at the identity provider provisions the user and opens a session
- A returning user is recognised and a wrong password stays at the provider
- A matching local account is linked to the identity
- A provider that does not provision accounts leaves the visitor on the login page
- A provider that is switched off cannot be used

The external identity provider is the `FakeOIDCProvider` of `libs/e2e-support`, served on its own port: the application discovers it, the browser signs in on its login page and the application redeems the code over HTTP. The tenant is resolved from the `/t/{slug}` path by a second live server that serves the same application behind the tenant middleware.
