# Introspection, revocation and userinfo

Applications validate a token locally with the JWKS, then ask the provider
whether it is still active, and read the profile of the user from
`/userinfo`. The [fake provider](07-fake-openid-provider.md) implements these
three endpoints with the answers of the auth application.

## Introspection

`POST /oauth2/introspect` (RFC 7662) takes `token` and an optional
`token_type_hint`.

- The caller authenticates as a client (Basic or form fields). A missing
  client is `401 invalid_client` (`Client authentication required`), a bad
  secret `401`, and a client whose `allowed_scopes` do not contain
  `introspect` gets `403 insufficient_scope`. Create the client of the
  application under test with `Client.service(..., ["introspect", ...])`.
- An active access token answers `active: true` with `scope`, `client_id`,
  `token_type` (`Bearer`), `exp`, `iat`, `sub`, `aud`, `iss` and `jti`.
- An active refresh token answers `active: true` with `token_type:
  refresh_token`. The hint only sets the lookup order; both kinds are found
  either way.
- Anything else, including a token that is revoked, expired, rotated, garbage
  or never issued, answers exactly `{"active": false}`.

## Revocation

`POST /oauth2/revoke` (RFC 7009) takes `token` and an optional hint, requires
client authentication like introspection (no `introspect` scope needed), and
always answers `200` with an empty body, whether or not the token existed.
A revoked access token is dead everywhere: introspection reports it inactive,
`/userinfo` refuses it and it is no longer accepted as a subject token. A
revoked refresh token fails at the token endpoint with `invalid_grant`.

To simulate an administrator ending sessions, call
`provider.revoke_tokens()` (every token) or
`provider.revoke_tokens(user_id=user.id)`. The application then sees its
tokens turn inactive at its next introspection.

## Userinfo

`GET` or `POST /userinfo` with `Authorization: Bearer <access token>` returns
the claims of the user that the token's scopes allow:

| Scope | Claims |
| --- | --- |
| (always) | `sub` (the same value as in the token) |
| `profile` | `name` and `picture`, when the user has them |
| `email` | `email`, `email_verified` |

Failures follow the auth application: `401` with `{"detail": "..."}` and a
`WWW-Authenticate: Bearer error="invalid_token"` header for a missing,
malformed, unknown, revoked or expired token, a token without a user or a
user who no longer exists, and `403` (`insufficient_scope`) when the token
lacks the `openid` scope. In particular the token obtained by a [token
exchange](09-oidc-token.md) usually has no `openid` scope and cannot call
`/userinfo`; applications use the login token for that.

## How it is tested

Pytest (`libs/e2e-support/tests/test_oidc_introspection.py`): the full body of
an active token, form-field authentication, never-issued, expired, rotated
and foreign tokens, refresh token introspection and hints, every client
authentication and scope failure, revocation of access and refresh tokens
and its effect on the other endpoints, the idempotent answer for unknown
tokens, public clients, `revoke_tokens` for all and one user, userinfo per
scope, with pairwise subjects, and each of its error answers.
