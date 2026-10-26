# Authentication

The statistics API described in the next pages must only be reachable by
authorised clients. This feature adds the building blocks: OIDC bearer token
validation, token introspection, optional scope checks through OAuth2 token
exchange, and two FastAPI dependencies. No route uses them yet; the statistics
routes do.

## How a request is checked

`analytics.auth` exports:

- `get_current_user`: dependency that requires a valid token and returns the
  `User`.
- `require_scopes(*scopes)`: dependency factory that requires a valid token
  that carries every listed scope.
- `User`: pydantic model built from the token claims (`id`, `email`, `name`,
  `scopes`, `is_machine_client`) with `has_scope`, `has_any_scope` and
  `has_all_scopes`.
- `jwt_validator` and `token_exchange_client`: the shared clients.

Steps of `require_scopes`:

1. Without `OAUTH2_ISSUER` the dependency answers `503 OAuth2 not
   configured`.
2. Without a bearer token it answers `401 Missing authorization token`.
3. If the confidential client is configured (`OAUTH2_CLIENT_ID` and
   `OAUTH2_CLIENT_SECRET`), the scopes are validated with an OAuth2 token
   exchange (RFC 8693) against the issuer; the scopes granted by the exchange
   are used. The error `invalid_grant` becomes `401`, `insufficient_scope`
   becomes `403`, any other error `401`.
4. Otherwise the token is validated directly (below) and the scopes found in
   its `scope` or `scp` claim must include the required ones, else `403` with
   a `WWW-Authenticate: Bearer error="insufficient_scope"` header.

### Token validation

`JWTValidator.validate_token_with_introspection`:

1. downloads the JWKS of the issuer (`{issuer}/.well-known/jwks.json`, cached
   in memory for one hour) and verifies the signature (`RS256` or `ES256`) and
   the issuer; the audience is not checked;
2. asks the introspection endpoint (`{issuer}/oauth2/introspect`, RFC 7662)
   whether the token is still active; a revoked token raises
   `TokenRevokedError` (`401 Token has been revoked`). If the introspection
   call itself fails the token is accepted, since the signature check already
   passed.

Introspection and token exchange results are cached in Redis for
`TOKEN_INTROSPECTION_CACHE_TTL` and `OAUTH2_CLIENT_CACHE_TTL` seconds. Redis
errors are logged and ignored: the caches are an optimisation.

### Scopes

`User.has_scope` supports the exact scope (`analytics:read`), a resource
wildcard (`analytics:*`) and the global wildcard (`*`). The scopes used by the
service are `analytics:read`, `analytics:write` and `analytics:delete`.

Subjects that are UUIDs are users; any other subject (the `client_id` of a
`client_credentials` token) produces a user with `is_machine_client=True`.

### Swagger UI

When `OAUTH2_ISSUER` and `OAUTH2_SWAGGER_CLIENT_ID` are set, the OpenAPI UI
(served only with `DOCS_ENABLED=true`) is configured for the authorization code
flow with PKCE using the public client. It requests the `openid`, `profile` and
`email` scopes only; the `analytics:*` scopes are checked by the server.

### Shutdown

The application lifespan closes the HTTP and Redis clients of
`jwt_validator` and `token_exchange_client` when the service stops.

## Settings

| Variable | Default | Description |
| --- | --- | --- |
| `OAUTH2_ISSUER` | empty | OIDC issuer URL; empty disables protected routes (`503`) |
| `OAUTH2_SWAGGER_CLIENT_ID` | empty | Public PKCE client used by Swagger UI |
| `OAUTH2_CLIENT_ID` | empty | Confidential client for introspection and token exchange |
| `OAUTH2_CLIENT_SECRET` | empty | Secret of the confidential client |
| `TOKEN_INTROSPECTION_CACHE_TTL` | `60` | Introspection cache lifetime in seconds |
| `OAUTH2_CLIENT_CACHE_TTL` | `300` | Token exchange cache lifetime in seconds |
| `REDIS_URL` | `redis://localhost:6379/7` | Redis used by the caches |
| `CACHE_TTL` | `300` | Declared in the settings, not used by the code |

`OAUTH2_CLIENT_SECRET` is also read from the systemd credential of the same
name (`$CREDENTIALS_DIRECTORY/OAUTH2_CLIENT_SECRET`) when it exists, which
takes priority over the environment variable. This lets a deployment keep the
secret out of the `.env` file.

`apps/analytics/compose.yml` now also starts a local Redis 7 on port 6380,
matching `.env.example`.

## Tests

pytest:

- `test_auth_models.py`: claims to `User` conversion (user, machine, scope
  formats) and scope matching.
- `test_auth_jwt.py`: JWKS download and caching, signature validation errors,
  introspection (active, revoked, failures, cache) and `close`.
- `test_auth_token_exchange.py`: configuration check, exchange request, error
  mapping, cache and `close`.
- `test_auth_dependencies.py`: both dependencies for every outcome (`401`,
  `403`, `503`, token exchange paths).
- `test_config.py`: OAuth2 and Redis defaults, `get_credential`, and the
  credential override of the client secret.
- `test_main.py`: Swagger configuration and the shutdown of the clients.

behave (`features/auth.feature`): the scenarios build a small FastAPI
application that uses the real dependencies, with fake token validation, so no
OIDC server or Redis is needed. `features/environment.py` sets a dummy
`OAUTH2_ISSUER` before the application is imported:

- A request without token is rejected
- An invalid token is rejected
- A revoked token is rejected
- A token with the required scope is accepted
- A token without the required scope is forbidden
- A resource wildcard grants every scope of the resource
- The global wildcard grants every scope
- A machine token is recognised
- The current user is built from the token claims
- Scopes can be checked with token exchange
- Token exchange refuses missing scopes
- Token exchange refuses expired tokens
- Protected routes answer 503 when no issuer is configured

The real signature validation, introspection and exchange HTTP calls are only
covered by the pytest tests with mocked HTTP clients.
