# OIDC authentication

API clients authenticate with a bearer token issued by the platform `auth`
service. apt-server never stores credentials: it validates tokens against the
OIDC provider and keeps only short-lived results in Redis.

## What it does

Two kinds of bearer tokens are accepted in `Authorization: Bearer <token>`:

- Signed JWTs (three dot-separated segments). The signature is checked
  against the provider JWKS (`RS256` or `ES256`, issuer and expiry verified,
  audience not checked), then the token is introspected to detect revocation.
- Opaque tokens, such as personal access tokens (`gab_pat_...`). They are
  validated by introspection only and must come back `active`.

`apt_server.auth` contains the building blocks:

| Module | Role |
| --- | --- |
| `jwks.py` | OIDC discovery, JWKS cache, JWT validation, multiple trusted issuers |
| `introspection.py` | RFC 7662 introspection with a Redis cache |
| `token_exchange.py` | RFC 8693 token exchange to check granted scopes, cached in Redis |
| `userinfo.py` | OIDC UserInfo client, cached in Redis |
| `models.py` | `User` built from the claims, scope matching with wildcards |
| `dependencies.py` | FastAPI dependencies `Auth`, `CurrentUser` and `require_scopes(...)` |

Scope matching accepts exact scopes, `*` (everything) and `prefix:*`
wildcards. A subject that is a UUID is a user, a subject equal to the
`client_id` claim (or not a UUID) is a machine client.

`require_scopes("apt:write")` builds a dependency that, for JWTs and when
token exchange is configured, asks the provider to exchange the token for the
requested scopes (`invalid_grant` gives 401, `insufficient_scope` gives 403).
Otherwise the scopes of the introspected claims are checked directly.

When the introspection call itself fails (network error, server error), the
token is treated as active: signature and expiry have already been verified,
and the failure is logged as a warning. Opaque tokens have no such fallback.

## Endpoints

| Endpoint | Auth | Description |
| --- | --- | --- |
| `GET /me` | bearer | `user_id`, `email`, `name`, `picture` (from UserInfo) and `scopes` |

Failures: 401 `Missing authorization token` (with `WWW-Authenticate:
Bearer`), 401 `Token has been revoked`, 401 `Invalid token`, 503 `OAuth2 not
configured` when `OAUTH2_ISSUER` is empty.

When `OAUTH2_ISSUER` is set, the OpenAPI schema declares an OAuth2
authorization code scheme so Swagger UI can log in; `OAUTH2_SWAGGER_CLIENT_ID`
enables PKCE for it. The lifespan closes every HTTP and Redis client on
shutdown.

## Settings

| Variable | Default | Description |
| --- | --- | --- |
| `OAUTH2_ISSUER` | empty | Issuer URL; empty disables authentication (503) |
| `OAUTH2_CLIENT_ID` | empty | Confidential client used for introspection and exchange |
| `OAUTH2_CLIENT_SECRET` | empty | Client secret, also read from systemd credentials |
| `OAUTH2_SWAGGER_CLIENT_ID` | empty | Public PKCE client for Swagger UI |
| `OAUTH2_TRUSTED_ISSUERS` | empty | Comma-separated extra accepted issuers |
| `OAUTH2_CLIENT_CACHE_TTL` | `300` | Token exchange cache lifetime (seconds) |
| `TOKEN_INTROSPECTION_CACHE_TTL` | `60` | Introspection cache lifetime (seconds) |
| `JWKS_CACHE_TTL` | `3600` | Discovery document and JWKS lifetime (seconds) |
| `USERINFO_CACHE_TTL` | `300` | UserInfo cache lifetime (seconds) |
| `REDIS_URL` | empty | Redis for the caches; empty disables caching |
| `REDIS_KEY_PREFIX` | `apt_server` | Prefix of every Redis key |

Secrets are looked up in the systemd credentials directory
(`CREDENTIALS_DIRECTORY`) first, then in the environment. Redis errors are
logged and never fail a request.

## Tests

- pytest: `tests/test_auth_models.py` (claims, machine clients, scope
  wildcards), `tests/test_auth_jwks.py` (real RS256 tokens: valid, expired,
  wrong issuer, wrong key, trusted issuers, discovery cache),
  `tests/test_auth_clients.py` (introspection, token exchange and UserInfo
  against `httpx.MockTransport` and a fake Redis) and
  `tests/test_auth_dependencies.py` (`/me`, revoked and opaque tokens,
  `require_scopes` with and without token exchange).
- behave: `features/oidc_authentication.feature` with the scenarios "A
  request without a token is rejected", "The service reports when OAuth2 is
  not configured", "A valid JWT identifies the caller", "A personal access
  token is validated by introspection", "A revoked token is refused" and "An
  unknown token is refused". The auth service is replaced by in-process
  fakes.
