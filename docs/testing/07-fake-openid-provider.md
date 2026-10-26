# Fake OpenID provider

Applications that log users in through OpenID Connect (`internal`,
`knowledge`, `apt-server`) depend on the auth application. A browser
scenario cannot use the real one, so `e2e_support.oidc.FakeOIDCProvider`
emulates it: an ASGI application, served by
[`LiveServer`](01-live-server.md), that speaks the same protocol with the
same rules. The applications need no change: only their `OAUTH2_ISSUER`
setting points to the fake.

This page covers the provider itself: its users and clients, discovery, keys
and the recording of requests. Its endpoints are documented on the following
pages.

## Creating a provider

```python
from e2e_support.oidc import Client, FakeOIDCProvider, User
from e2e_support.server import LiveServer

provider = FakeOIDCProvider(
    users=[User(email="ada@example.test", name="Ada", scopes=("billing:read",))],
    clients=[Client.public("web", ["http://127.0.0.1:*/auth/callback"])],
)
with LiveServer(provider) as server:
    assert provider.issuer == server.url
```

The issuer is the base URL of the server. A `LiveServer` tells the provider
its URL through the `bind_url` hook, so there is nothing to configure; pass
`issuer="https://auth.example.test"` only to serve the provider some other
way. The issuer cannot have a path. The application under test must be
configured with exactly this URL (it compares the `iss` claim of the tokens).

| Option | Default | Description |
| --- | --- | --- |
| `users`, `clients` | empty | Initial users and clients; add more with `add_user` and `add_client` |
| `issuer` | learned from the server | Public base URL |
| `auto_approve` | `False` | Skip the login and consent pages |
| `require_consent` | `False` | Show a consent page after login |
| `pairwise_subjects` | `False` | Derive a different `sub` per client, like the auth application, instead of the user id |
| `access_token_ttl` | `3600` | Access token lifetime, seconds (a client can override it) |
| `refresh_token_ttl` | 30 days | Refresh token lifetime, seconds |
| `code_ttl` | `600` | Authorization code lifetime, seconds |
| `id_token_ttl` | `3600` | ID token lifetime, seconds |
| `signing_key` | generated | A `SigningKey` to share between providers |

## Users

`User(email, name="", id=<random UUID>, scopes=(), password=None, mfa="none",
email_verified=True, picture=None)`.

- `id` must be a UUID, because the applications parse the `sub` claim as one.
- `scopes` are the permissions the user holds through roles in the real auth
  application (`vpn:admin`, `billing:*`, `*`). They are **not** in the tokens
  of a plain login, which only carry the OIDC scopes; an application obtains
  them through a token exchange, which grants the requested scopes that the user
  holds.
- `password`: when set, the login page requires it; when `None` any password
  is accepted.
- `mfa` only accepts `"none"`: multi-factor flows are not emulated.

## Clients

`Client(client_id, client_secret=None, redirect_uris=(), allowed_scopes=openid
profile email offline_access, grant_types=(authorization_code, refresh_token),
require_pkce=True, access_token_ttl=None, is_active=True)`.

- A client with a secret is confidential and must authenticate at the
  token, introspection and revocation endpoints; without one it is public.
- `redirect_uris` are exact URIs or patterns where `*` matches any
  characters (`http://127.0.0.1:*/auth/callback` suits an application on a
  random port). Empty accepts any URI.
- `allowed_scopes` accept wildcards (`billing:*`, `*`) and bound what the
  client can request, as in the auth application.
- Two constructors cover the usual cases: `Client.public(client_id,
  redirect_uris)` for a browser front end using PKCE, and
  `Client.service(client_id, client_secret, allowed_scopes)` for a
  confidential service allowed to use client credentials, token exchange and
  refresh. List `introspect` in the allowed scopes of a client that calls the
  introspection endpoint.

## Discovery and keys

- `GET /.well-known/openid-configuration` returns the discovery document with
  the endpoints and capabilities of the auth application (only what the fake
  implements: the `code` response type, the four grants, `S256` and `plain`
  PKCE, RS256).
- `GET /.well-known/jwks.json` publishes the public RS256 key. A key pair is
  generated for every provider (`provider.key`, a `SigningKey` with `kid`,
  `public_jwk()` and `sign(claims)`), so tokens verify against the JWKS like
  real ones.

## Recording requests

Every request is recorded as a `RecordedRequest` (`method`, `path`, `query`,
`form`, `headers`, `status`, `response_body`, plus `json` and `params`
helpers) before the client sees the end of the response.

| Member | Description |
| --- | --- |
| `provider.requests` | All requests, oldest first |
| `requests_to(path, method=None)` | Requests for a path |
| `last_request(path)` | The latest one; `LookupError` when there is none |
| `clear_requests()` | Forget everything |

```python
record = provider.last_request("/oauth2/token")
assert record.form["grant_type"] == "authorization_code"
assert record.status == 200
```

## How it is tested

Pytest (`libs/e2e-support/tests/test_oidc_core.py`): issuer learned from the
server, explicit and unknown issuers, the discovery document (served and
in-process), pairwise advertisement, a JWKS key verifying a token signed by
the provider, request recording and its helpers, adding users and clients,
user validation (UUID, MFA) and the three scope-matching rules.
