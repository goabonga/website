# OAuth2 authentication

Protected routes require a bearer token issued by the platform identity
provider. This feature provides the token validation clients and the FastAPI
dependencies the route features use to protect themselves.

## How a request is authenticated

1. The token is read from the `Authorization: Bearer` header. When an OAuth2
   issuer and a Swagger client are configured, the same scheme drives the
   Swagger UI authorization-code flow with PKCE.
2. If no token is present the request is rejected with `401`. If
   `OAUTH2_ISSUER` is empty the service answers `503` (OAuth2 not
   configured).
3. A JWT-shaped token (three dot-separated segments) is verified against the
   issuer JWKS and then checked by introspection when the confidential client
   is configured (if the introspection request itself fails, the token is
   treated as active). Any other token is treated as an opaque personal
   access token and validated by introspection only. Revoked tokens give
   `401`.
4. When a confidential client (`OAUTH2_CLIENT_ID` and `OAUTH2_CLIENT_SECRET`)
   is configured, JWTs go through an OAuth2 token exchange that asks the
   identity provider whether the required scopes are granted
   (`invalid_grant` gives `401`, `insufficient_scope` gives `403`).
   Otherwise the scopes are read from the validated claims. The identity of
   the caller always comes from the original, validated token, never from
   the exchanged one, which is issued to this service.
5. Missing scopes give `403`. Scopes may end with `:*` (for example
   `mailler:*`) to grant every scope of a namespace, and `*` grants
   everything.

Introspection and token exchange results are cached in Redis (key prefix
`REDIS_KEY_PREFIX`); the JWKS is cached in memory. When Redis is unavailable
the caches are skipped.

## Client identity and administration

Several applications (clients) share the service and each one only sees its
own data. The client of a call is the OAuth2 client the token was issued to:
the `client_id` claim, or the authorized party (`azp`) when that claim is
absent. A token that carries neither is refused with `403`, except when it
holds the administration scope.

The administration scope is named by `ADMIN_SCOPE`. A caller holding it (or
a wildcard such as `mailler:*`, which covers it) is an administrator and can
cross the client boundary; when token exchange is configured the scope must
also be granted by the identity provider. The resulting `AuthContext`
exposes the helpers the route features use to enforce the boundary:

| Helper | Behaviour |
| --- | --- |
| `client_id` | Client of the caller |
| `is_admin` | Whether the caller holds the administration scope |
| `owns(owner)` | True when the resource belongs to the caller's client, or the caller is an administrator |
| `restrict(stmt, column, client_id=None)` | Restricts a query to the caller's client; an administrator sees every client unless `client_id` narrows the query; a regular caller asking for another client gets `403` |
| `target_client_id(requested=None)` | Client a call acts on: the caller's own, or the one named by `requested` when the caller is an administrator (`403` otherwise) |
| `require_client_id()` | Client of the caller, `403` when the token carries none |

## Building blocks

| Module | Role |
| --- | --- |
| `mailler.auth.jwks` | `jwks_manager`: fetches and caches the issuer JWKS, verifies JWT signatures against the issuer and the trusted issuers |
| `mailler.auth.introspection` | `introspection_client`: RFC 7662 token introspection with Redis cache and revocation detection |
| `mailler.auth.token_exchange` | `token_exchange_client`: scope validation through OAuth2 token exchange with Redis cache |
| `mailler.auth.models` | `User` built from JWT claims (user tokens and machine clients) with wildcard scope matching |
| `mailler.auth.dependencies` | `get_auth_context`, `get_current_user` and `require_scopes(*scopes)` returning an `AuthContext` |

Route features declare their protection with
`Depends(require_scopes("mailler:read"))`. The scopes used by the
application are `mailler:send`, `mailler:read`, `mailler:write`,
`mailler:stats` and `mailler:webhooks`; each feature page states which ones
it requires.

The application lifespan closes the three clients on shutdown, and the
OpenAPI description documents the scheme. The authenticated user id and
client id are attached to every log record of the request.

## Settings

| Variable | Default | Description |
| --- | --- | --- |
| `OAUTH2_ISSUER` | empty | OIDC issuer; empty disables authentication (503) |
| `OAUTH2_CLIENT_ID` | empty | Confidential client used for introspection and token exchange |
| `OAUTH2_CLIENT_SECRET` | empty | Secret of that client (secret) |
| `OAUTH2_SWAGGER_CLIENT_ID` | empty | Public PKCE client used by the Swagger UI |
| `ADMIN_SCOPE` | `mailler:admin` | Scope that lets a caller cross the client boundary |
| `OAUTH2_TRUSTED_ISSUERS` | empty | Additional trusted issuers, comma separated |
| `OAUTH2_CLIENT_CACHE_TTL` | `300` | Token exchange cache TTL in seconds |
| `TOKEN_INTROSPECTION_CACHE_TTL` | `60` | Introspection cache TTL in seconds |
| `JWKS_CACHE_TTL` | `3600` | JWKS cache TTL in seconds |
| `REDIS_URL` | `redis://localhost:6379/11` | Redis used for the caches |
| `REDIS_KEY_PREFIX` | `mailler` | Cache key prefix |

Secrets can also be provided as systemd credentials: when
`CREDENTIALS_DIRECTORY` is set, a file named after the variable (for example
`OAUTH2_CLIENT_SECRET`) takes precedence over the environment
(`mailler.config.get_credential`). Later features reuse this mechanism for
their own secrets.

## Dependencies

`PyJWT[crypto]` (JWT verification), `httpx` (calls to the identity provider)
and `redis` (caches).

## How it is tested

- pytest: `tests/test_auth_dependencies.py`, `tests/test_auth_introspection.py`,
  `tests/test_auth_jwks.py`, `tests/test_auth_models.py`,
  `tests/test_auth_token_exchange.py`, plus authentication cases in
  `tests/test_main.py` and `tests/test_config.py` (client ownership helpers,
  administration scope with and without token exchange, `azp` fallback).
- behave: `features/authentication.feature`. The scenarios replace the three
  validation clients with an in-memory token table and exercise scope
  checks and client identity through three probe routes registered by
  `features/environment.py`; no identity provider or Redis is involved.
