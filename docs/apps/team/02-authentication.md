# OAuth2 authentication

Every route of the platform, except `/health`, requires a bearer token issued
by the authentication server of the platform (an OIDC provider). This feature
adds the `team.auth` package: token validation, scope checks and the
authenticated user. It adds no endpoint by itself; the routes of the following
features declare the scopes they need.

## What it provides

- `team.auth.require_scopes(*scopes)`: FastAPI dependency factory. A route
  declares `Depends(require_scopes("team:platform:read"))` and receives an
  `AuthContext` with the `User`, its `user_id` and its `scopes`.
- `team.auth.get_auth_context` / `Auth` / `CurrentUser`: dependencies that
  authenticate without checking any scope.
- `team.auth.User`: the authenticated principal, built from the claims of the
  token. A token whose `client_id` claim equals its subject, or whose subject
  is not a UUID, is a machine token (`client_credentials` grant) and the user
  has `is_machine_client = True`. Scopes come from the `scope` claim (space
  separated string) or the `scp` claim (list). Wildcards are supported:
  `*` matches everything and `team:*` matches every scope starting with
  `team:`.
- `team.auth.jwks.jwks_manager`: discovers the JWKS of the issuer through
  `/.well-known/openid-configuration` and verifies the signature (`RS256`,
  `ES256`), the expiry and the issuer of JWT access tokens. Additional issuers
  can be trusted with `OAUTH2_TRUSTED_ISSUERS`.
- `team.auth.introspection.introspection_client`: RFC 7662 token
  introspection, used to detect revoked tokens and to validate opaque tokens
  (personal access tokens). Results are cached in Redis.
- `team.auth.token_exchange.token_exchange_client`: RFC 8693 token exchange,
  used to ask the authentication server whether the token really carries the
  scopes required by a route. Results are cached in Redis.
- `team.services.token_exchange`: a second token exchange client with its own
  cache, `get_token_exchange_client()`, for exchanging a user token on behalf of
  the service. Nothing in the application calls it yet.

## How a request is authenticated

1. The token is read from the `Authorization: Bearer` header (or through the
   OAuth2 authorization code scheme when `OAUTH2_ISSUER` is set, so that
   Swagger UI can sign in with PKCE). No token: `401 Missing authorization token`.
2. If `OAUTH2_ISSUER` is empty the server cannot validate anything and answers
   `503 OAuth2 not configured`.
3. A token made of three dot-separated segments is a JWT. When token exchange
   is configured (client id, client secret and issuer are set), the scopes of
   the route are validated by exchanging the token; the granted scopes replace
   the ones of the token. A refused exchange gives `401` (`invalid_grant`) or
   `403 Insufficient scopes. Required: ...` (`insufficient_scope`).
4. Otherwise the signature is verified with the JWKS and the token is
   introspected. A revoked token gives `401 Token has been revoked`, any other
   failure `401 Invalid token`. If introspection itself is unavailable the
   token is accepted (fail open) after the signature check.
5. Any other token is opaque and is validated by introspection only.
6. The scopes of the user are compared with the required ones. Missing scopes
   give `403 Insufficient scopes. Missing: ...`.
7. The user id and the client id are stored in the logging context (see
   [Foundation](01-foundation.md)) and on `request.state`.

The scopes used by the application are `team:platform:read` and
`team:platform:write` (platform objects), `team:read` and `team:write`
(messages and usage reports).

## Settings

| Variable | Default | Description |
|----------|---------|-------------|
| `OAUTH2_ISSUER` | empty | Base URL of the OIDC issuer; empty disables authentication (every route answers 503) |
| `OAUTH2_SWAGGER_CLIENT_ID` | empty | Public client used by Swagger UI (PKCE); needs the issuer |
| `OAUTH2_CLIENT_ID` | empty | Confidential client used for introspection and token exchange |
| `OAUTH2_CLIENT_SECRET` | empty | Secret of that client, read as a credential (see [Foundation](01-foundation.md)) |
| `OAUTH2_TRUSTED_ISSUERS` | empty | Comma separated list of additional accepted issuers |
| `JWKS_CACHE_TTL` | `3600` | Seconds to cache the discovery document and the signing keys |
| `TOKEN_INTROSPECTION_CACHE_TTL` | `60` | Seconds to cache an introspection result |
| `OAUTH2_CLIENT_CACHE_TTL` | `300` | Seconds to cache a token exchange result |
| `OAUTH2_TOKEN_CACHE_TTL` | `300` | Same, for `team.services.token_exchange` |
| `OAUTH2_INTROSPECTION_CACHE_TTL` | `60` | Declared for compatibility; not read by the code |
| `REDIS_URL` | `redis://localhost:6379/10` | Redis used for the caches; empty disables caching |
| `REDIS_KEY_PREFIX` | `team` | Prefix of the cache keys |

`OAUTH2_CLIENT_SECRET` is the only secret. The application module also
changes: its lifespan closes the three clients on shutdown, and the OpenAPI
description lists the scopes.

## Tests

pytest covers the user model (`tests/test_auth_models.py`), the JWKS manager
(`tests/test_auth_jwks.py`), introspection (`tests/test_auth_introspection.py`),
both token exchange clients (`tests/test_auth_token_exchange.py`,
`tests/test_services_token_exchange.py`), the dependencies
(`tests/test_auth_dependencies.py`), and the new lifespan and Swagger
configuration cases in `tests/test_main.py`. `tests/conftest.py` gains the
`auth_client` and `admin_client` fixtures, which patch the three clients and
authenticate every request as a user holding the four scopes above (or the
`team:*` wildcard).

behave (`features/authentication.feature`) protects a small application with
`require_scopes` and plays the authentication server in memory:

- A request without a token is rejected
- A valid token with the required scope is accepted
- A token without the required scope is refused
- A wildcard scope grants every scope of its namespace
- A wildcard scope does not grant another namespace
- A machine client token is recognised
- A revoked token is refused
- A token rejected by the authentication server is refused
- An opaque token is validated by introspection only
- The service answers 503 when OAuth2 is not configured
- Token exchange refuses a token that lacks the scope
- Scopes can be listed in the token as a string or as a list

No network or Redis is involved: the three clients are replaced by fakes.
