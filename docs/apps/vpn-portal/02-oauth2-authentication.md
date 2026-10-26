# OAuth2 authentication

The portal never issues tokens. It validates the access tokens handed out by
the platform OAuth2 / OIDC server (the `auth` application) and decides, for
each route, whether the caller holds the required `vpn:*` scope. This
feature adds the building blocks; the routes that use them arrive with the
next features.

## What it does

- **JWKS validation** (`vpn_portal.auth.jwks.JWKSManager`): discovers the
  signing keys through `<issuer>/.well-known/openid-configuration`, verifies
  the signature (`RS256`, `ES256`), the expiry, the issued-at time and the
  issuer. The primary issuer and the optional comma-separated
  `OAUTH2_TRUSTED_ISSUERS` are accepted. Discovery and keys are cached for
  `JWKS_CACHE_TTL` seconds.
- **Introspection** (`IntrospectionClient`, RFC 7662): after a successful
  signature check, asks `<issuer>/oauth2/introspect` whether the token is
  still active, so revoked tokens are refused. The answer is cached in
  Redis for `TOKEN_INTROSPECTION_CACHE_TTL` seconds. When the confidential
  client is not configured, or when the introspection request fails, the
  token is considered active (fail open, with a warning in the log).
  Opaque tokens (personal access tokens, which are not three dot-separated
  segments) are validated by introspection alone.
- **Token exchange** (`TokenExchangeClient`, RFC 8693): to learn which of
  the required scopes the user really holds (RBAC lives in the auth
  service), the portal exchanges the user token for a token limited to those
  scopes. The result is cached in Redis for `OAUTH2_CLIENT_CACHE_TTL`
  seconds. A refused exchange maps to `401` (`invalid_grant`) or `403`
  (`insufficient_scope`).
- **FastAPI dependencies** (`vpn_portal.auth.dependencies`):
  `get_auth_context` (any valid token), `get_current_user`, and
  `require_scopes(*scopes)` which returns an `AuthContext` or raises
  `401`, `403` or `503` (OAuth2 not configured). Without token exchange the
  scopes of the token itself are checked, with wildcard support (`*`,
  `vpn:*`). The request context used by the logs (`user`, `client`) is
  filled from the token.
- **`User` model** (`vpn_portal.auth.models.User`): built from the claims;
  recognises machine tokens (`client_credentials`, where `sub` equals
  `client_id` or is not a UUID), reads `scope` or `scp` as a string or a
  list.
- **Swagger UI**: when `OAUTH2_ISSUER` and `OAUTH2_SWAGGER_CLIENT_ID` are
  set, the documentation page offers the authorization-code flow with PKCE
  and asks only for `openid`, `profile` and `email`. The lifespan handler
  closes the HTTP and Redis clients on shutdown.

## Settings

| Variable | Default | Description |
| --- | --- | --- |
| `OAUTH2_ISSUER` | empty | OIDC issuer URL; when empty every protected route answers `503` |
| `OAUTH2_SWAGGER_CLIENT_ID` | empty | Public PKCE client used by Swagger UI |
| `OAUTH2_CLIENT_ID` | empty | Confidential client used for token exchange and introspection |
| `OAUTH2_CLIENT_SECRET` | empty | Secret of that client (see below) |
| `OAUTH2_CLIENT_CACHE_TTL` | `300` | Token exchange cache TTL, in seconds |
| `TOKEN_INTROSPECTION_CACHE_TTL` | `60` | Introspection cache TTL, in seconds |
| `JWKS_CACHE_TTL` | `3600` | Discovery document and key set cache TTL, in seconds |
| `OAUTH2_TRUSTED_ISSUERS` | empty | Extra accepted issuers, comma separated |
| `REDIS_URL` | empty | Redis URL for the caches; without it nothing is cached |
| `REDIS_KEY_PREFIX` | `vpn` | Prefix of the cache keys |

`OAUTH2_CLIENT_SECRET` is a secret. It is read from the systemd credential
of the same name (`$CREDENTIALS_DIRECTORY/OAUTH2_CLIENT_SECRET`) first and
from the environment otherwise (`vpn_portal.config.get_credential`).

The OAuth2 scheme is built when `vpn_portal.auth.dependencies` is imported,
so `OAUTH2_ISSUER` must be set before the application starts.

## Data model

None. The only state is the Redis cache.

## Tests

- pytest: `tests/test_auth_models.py`, `test_auth_jwks.py`,
  `test_auth_introspection.py`, `test_auth_token_exchange.py` and
  `test_auth_dependencies.py` (unit tests of each module, with the network
  and Redis mocked), `test_auth_endpoints.py` (the dependencies on a minimal
  FastAPI application), `test_main.py` (Swagger configuration, lifespan
  cleanup) and the new cases of `test_config.py`.
- behave: `features/oauth2.feature`, run on a minimal application that uses
  the real `require_scopes`; JWKS, introspection and token exchange are
  replaced by mocks. Scenarios: *Request without a token*, *JWT carrying
  the required scope*, *JWT missing the required scope*, *Wildcard scope
  covers the required scope*, *Revoked token*, *Invalid token signature*,
  *Opaque personal access token*, *Token exchange grants the scope*, *Token
  exchange refuses the scope*, *OAuth2 is not configured*, *Machine client
  token* and *User token*.
