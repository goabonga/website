# Token endpoint

`POST /oauth2/token` of the [fake provider](07-fake-openid-provider.md)
implements the four grants that the applications use. Checks, ordering and
error codes follow the auth application, so errors can be provoked on
purpose and the application's handling asserted.

## Client authentication

The client is identified by `client_id` and, if it is confidential, a
secret, sent in an `Authorization: Basic` header (which wins) or as form
fields.

| Situation | Answer |
| --- | --- |
| No `client_id` | `400 invalid_request` (`client_id is required`) |
| Unknown or inactive client | `401 invalid_client` (`Invalid client`) |
| Confidential client without or with a wrong secret | `401 invalid_client` (`Client authentication required`, `Invalid client credentials`) |
| `grant_type` not in the client's `grant_types` | `400 unauthorized_client` |
| `grant_type` known to nobody | `400 unsupported_grant_type` |

Failures are `{"detail": {"error": ..., "error_description": ...}}`, the
shape the auth application answers with, and a 401 carries
`WWW-Authenticate: Basic`. Success is a JSON object with `access_token`,
`token_type` (`Bearer`), `expires_in`, and, depending on the grant,
`refresh_token`, `scope` and `id_token`.

## Tokens

Access tokens are RS256 JWTs signed with the key published in the JWKS, with
the claims of the auth application: `iss`, `sub`, `aud` (the client id, or
the requested audience), `exp`, `iat`, `jti`, `scope`, `client_id`, plus
`nonce` and `act` when relevant. They carry no email or name: applications
fetch those from `/userinfo`, as with the real service. `sub` is the user id
(or the client id for client credentials); with `pairwise_subjects=True` it
is a UUID derived from the user and the client. The lifetime is
`access_token_ttl`, overridable per client.

The ID token (when `openid` was granted) has `iss`, `sub`, `aud`, `exp`,
`iat`, `nonce`, `auth_time` and `at_hash`.

## Grants

**`authorization_code`** - redeems the code of the [authorization
endpoint](08-oidc-authorization.md). Requires `code` and `redirect_uri`. The
code must exist, be unused and unexpired, belong to the client and the same
redirect URI. When a PKCE challenge was sent, `code_verifier` is required,
must be 43 to 128 unreserved characters and must match the challenge
(`S256` or `plain`), otherwise `invalid_grant` (`PKCE verification failed`).
A failed PKCE check does not burn the code; a successful redemption does, and
a replay is `invalid_grant`. Returns access token, refresh token and, with
`openid`, an ID token.

**`refresh_token`** - rotates the refresh token: the old one is revoked
and a new access/refresh pair is returned. A `scope` parameter can narrow the
scopes but not widen them (`invalid_scope`). The token must belong to the
client and not be expired (`refresh_token_ttl`).

**`client_credentials`** - for confidential clients only. Without `scope`, all
the client's allowed scopes are granted (a literal `*` stays `*`); requested
scopes must match the allowed ones, wildcards included (`billing:*`).
No user, no refresh token.

**`urn:ietf:params:oauth:grant-type:token-exchange`** (RFC 8693) - for
confidential clients only. This is how `internal`, `knowledge` and `apt-server`
turn the user's login token into a token with the scopes of their roles.

1. The subject token (`subject_token_type` is `...:access_token` or
   `...:jwt`) must be a token this provider issued, not revoked and not
   expired; a `jwt` is only decoded.
2. The requested scopes (default: those of the subject token) are filtered by
   what the exchanging client may ask for: exact, `*`, `<resource>:*` and
   `internal:*`. If none remains: `invalid_scope`.
3. For a subject with a user, a scope is **granted when it is already in the
   subject token or when the user holds it** through its `scopes`
   (`*`, exact or `<resource>:*`). If none is granted:
   `insufficient_scope`, naming the denied scopes. For a subject without a
   user (client credentials), only the scopes already in the token survive.
4. `audience` (or `resource`) becomes `aud`; a decoded `actor_token`
   becomes the `act` claim. No refresh token is returned.

So the granted scopes are exactly *requested ∩ allowed for the client ∩ held
by the user*, and a test can configure a user with `scopes=("billing:read",)`
to check that an application hides what that user may not see.

```python
user = User(email="ada@example.test", scopes=("billing:read", "vpn:*"))
client = Client.service("internal-api", "s3cret", ["openid", "billing:*", "vpn:*", "introspect"])
# Exchanging ada's token for "billing:read billing:write vpn:admin" grants
# "billing:read vpn:admin": ada does not hold billing:write.
```

## Time

All expirations use `provider.now()`, which calls `provider.clock`
(`time.time` by default). Replace `clock` to age codes and tokens inside a
test. Note that the signed `exp` of tokens already issued cannot change, so
for an application that validates it use a short `access_token_ttl`.

## How it is tested

Pytest (`libs/e2e-support/tests/test_oidc_token.py`) against a live
provider: the code exchange, the claims of access and ID tokens verified with
the published JWKS, replay, expiry, every validation message, PKCE failures
not burning the code, per-client lifetimes, pairwise subjects, Basic and
form authentication and every failure of it, refresh rotation and scope
narrowing, client credentials and their scope rules, and the token exchange
(granted, denied, super user, client allowance, default scopes, audience and
actor, JWT subjects, subjects without user, revoked and expired subjects,
parameter validation, confidential clients only).
