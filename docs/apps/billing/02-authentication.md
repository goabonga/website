# Authentication

Every endpoint except `/health` is protected by OAuth2 bearer tokens issued
by the `auth` application. The `billing.auth` package validates tokens and
checks the `billing:*` scopes; routes opt in with the `require_scopes`
dependency, so this feature changes no endpoint by itself.

## How a request is authenticated

1. The token is read from the `Authorization: Bearer` header. When
   `OAUTH2_ISSUER` is set the dependency is an OAuth2 authorization-code
   scheme, which also lets the Swagger UI log in with PKCE.
2. Without a token the request is answered `401`. When no issuer is
   configured the service answers `503 OAuth2 not configured`.
3. A token made of three dot-separated segments is treated as a JWT. Its
   signature is verified against the JWKS of the issuer (RS256 or ES256,
   issuer check and expiry check, no audience check), then an RFC 7662
   introspection call confirms it was not revoked.
4. Any other token (for example a personal access token) is opaque: it is
   validated by introspection only.
5. For JWTs, when token exchange is configured, the scopes required by the
   route are requested through an RFC 8693 token exchange; the scopes
   granted by the exchange replace the ones of the token. Otherwise the
   scopes found in the token claims (`scope` or `scp`) are used.
6. Missing scopes give `403`, with a `WWW-Authenticate` header naming the
   required scopes.

Revoked or invalid tokens give `401`. The user and client identifiers are
stored in the request state and in the logging context.

## Scopes

A `User` is built from the claims. A subject that is not a UUID, or a
`client_id` claim equal to the subject, marks a machine client. Scope
matching supports wildcards: `*` grants everything and `billing:*` grants
every scope starting with `billing:`.

| Scope | Used by |
|-------|---------|
| `billing:platform:read` | Read access to the platform endpoints |
| `billing:platform:write` | Management of SaaS applications, products, prices, customers, subscriptions |
| `billing:usage:write` | Usage reporting |
| `billing:checkout:write` | Checkout sessions |
| `billing:webhooks` | Stripe events forwarded by the `webhooks` application |

The routes that use them are introduced by the later features.

## Using the dependency

```python
from fastapi import Depends
from billing.auth import AuthContext, require_scopes

@router.get("/resource")
async def read(auth: AuthContext = Depends(require_scopes("billing:platform:read"))):
    ...
```

`get_auth_context` and `get_current_user` are also available when only an
authenticated user is needed.

## Caching and failure modes

- Introspection results and token exchange results are cached in Redis
  (`REDIS_URL`, keys prefixed with `REDIS_KEY_PREFIX`). Redis errors are
  logged and ignored.
- Introspection is fail-open: if the introspection service cannot be
  reached, a validly signed JWT is still accepted. Opaque tokens are
  fail-closed.
- The JWKS and the discovery document are cached for `JWKS_CACHE_TTL`
  seconds.
- The lifespan handler of the application closes the HTTP and Redis clients
  of the three components on shutdown.

## Configuration

| Variable | Default | Purpose |
|----------|---------|---------|
| `REDIS_URL` | `redis://localhost:6379/10` | Cache for token validation results |
| `REDIS_KEY_PREFIX` | `billing` | Cache key prefix |
| `OAUTH2_ISSUER` | empty | Primary OIDC issuer; empty disables authentication (503) |
| `OAUTH2_TRUSTED_ISSUERS` | empty | Comma-separated additional issuers |
| `OAUTH2_SWAGGER_CLIENT_ID` | empty | Public PKCE client used by the Swagger UI |
| `OAUTH2_CLIENT_ID` | empty | Confidential client for introspection and token exchange |
| `OAUTH2_CLIENT_SECRET` | empty | Confidential client secret (secret) |
| `TOKEN_INTROSPECTION_CACHE_TTL` | `60` | Introspection cache TTL, seconds |
| `OAUTH2_CLIENT_CACHE_TTL` | `300` | Token exchange cache TTL, seconds |
| `JWKS_CACHE_TTL` | `3600` | JWKS cache TTL, seconds |
| `OAUTH2_HTTP_TIMEOUT` | `10.0` | Timeout of the calls to the auth service (discovery, JWKS, introspection, token exchange), seconds |

`OAUTH2_CLIENT_SECRET` is first looked up as a systemd credential in
`$CREDENTIALS_DIRECTORY` (file named `OAUTH2_CLIENT_SECRET`), then in the
environment (`billing.config.get_credential`).

The Swagger UI login is enabled only when both `OAUTH2_ISSUER` and
`OAUTH2_SWAGGER_CLIENT_ID` are set; it requests only the `openid`,
`profile` and `email` scopes.

## How it is tested

pytest (`apps/billing/tests`):

- `test_auth_models.py`: user construction from claims, machine clients,
  wildcard scopes;
- `test_auth_jwks.py`: discovery, JWKS client, token validation errors;
- `test_auth_introspection.py`: active and revoked tokens, cache, opaque
  tokens;
- `test_auth_token_exchange.py`: exchange request, error mapping, cache;
- `test_auth_dependencies.py`: bearer extraction, 401/403/503 answers,
  scope checks, token exchange path;
- `test_config.py` and `test_main.py` gain the credential lookup, the OAuth2
  settings, the Swagger configuration and the shutdown of the clients.

behave (`apps/billing/features/auth.feature`), against a small application
guarded by `require_scopes` with faked token validation:

- A request without token is rejected;
- An unknown token is rejected;
- A token carrying the required scope is accepted;
- The billing wildcard scope grants every scope;
- A token without the required scope is forbidden;
- An opaque token is validated by introspection.
