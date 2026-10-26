# OAuth2 authentication

API requests are authenticated with an OAuth2 bearer token issued by the
platform authentication service (an OIDC provider). The service validates the
token locally, optionally checks that it was not revoked, exchanges it for
the API scopes the user is entitled to and resolves the tenant of the
request.

## Request flow

`knowledge.auth.dependencies.get_auth_context` is the FastAPI dependency
behind every protected endpoint:

1. The token is read from the `Authorization: Bearer <jwt>` header, or from
   the OAuth2 authorization-code scheme used by the Swagger UI when
   `OAUTH2_SWAGGER_CLIENT_ID` is configured. Without a token the response is
   `401 Missing authentication`. Without `OAUTH2_ISSUER` it is a `500`.
2. `JWTValidator` (`knowledge.auth.jwt`) verifies the signature against the
   issuer JWKS (`<issuer>/.well-known/jwks.json`, RS256 and ES256, keys cached
   for one hour), the issuer, `exp`, `iat` and the presence of `sub`. Any
   failure is a `401`.
3. Revocation is checked through the introspection endpoint
   (`<issuer>/oauth2/introspect`, RFC 7662) when a confidential client is
   configured. If the endpoint is unreachable or answers with an error the
   token is accepted (graceful degradation); an explicit `active: false`
   rejects it.
4. When `OAUTH2_CLIENT_ID` and `OAUTH2_CLIENT_SECRET` are set, the token is
   exchanged (RFC 8693, `<issuer>/oauth2/token`) for the API scopes
   `collections:read`, `collections:write`, `collections:search`,
   `documents:read` and `documents:write`. The authorization service filters
   them by the user's roles and the granted scopes replace the `scope` claim.
   Exchange results are cached in Redis for `OAUTH2_TOKEN_CACHE_TTL` seconds;
   a Redis or exchange failure is logged and the original token scopes are
   kept.
5. The tenant is the UUID of the `X-Tenant-ID` header (`400` when it is not a
   UUID). Without the header, the first organization the user is a member of
   (if still active) is used; otherwise the tenant defaults to the user id,
   the personal tenant. The tenant id is stored in `request.state.tenant_id`.

The result is an `AuthContext` exposing `user`, `user_id`, `tenant_id`,
`scopes`, `has_scope()` and `require_scope()` (`403 Missing required scope:
<scope>`).

## Building blocks

| Name | Purpose |
| --- | --- |
| `get_auth_context` / `Auth` | Authenticated context, `401` when anonymous. |
| `get_optional_auth_context` / `OptionalAuth` | Context or `None`, never raises for bad tokens. |
| `get_current_user` / `CurrentUser` | The `User` of the context. |
| `get_optional_user` / `OptionalUser` | The `User` or `None`. |
| `require_scopes(*scopes)` | Dependency factory that enforces scopes and returns the context. |

`User` (`knowledge.auth.models`) is built from the JWT claims
(`from_jwt_claims`): the identifier comes from `sub`, the name from `name`,
`displayName`, `display_name` or `given_name`, the nickname from `nickname` or
`preferred_username`, and `scope` may be a space-separated string or a list.
Scope matching supports `*` (everything) and namespace wildcards such as
`documents:*`; `can_read`, `can_write` and `can_delete` are shortcuts for the
`<resource>:read`, `:write` and `:delete` scopes (delete is also granted by
write).

The singletons returned by `get_jwt_validator()` and
`get_token_exchange_client()` are closed when the application shuts down
(`lifespan`), and the Swagger UI is wired for the PKCE authorization-code
flow when both `OAUTH2_ISSUER` and `OAUTH2_SWAGGER_CLIENT_ID` are set
(`get_swagger_oauth2_config`).

## Settings

| Variable | Default | Description |
| --- | --- | --- |
| `OAUTH2_ISSUER` | empty | Issuer URL of the authentication service. Required for any authenticated request. |
| `OAUTH2_SWAGGER_CLIENT_ID` | empty | Public PKCE client used by the Swagger UI login. |
| `OAUTH2_CLIENT_ID` | empty | Confidential client used for token exchange and introspection. |
| `OAUTH2_CLIENT_SECRET` | empty | Secret of the confidential client. Read through `get_credential`, so it can come from a systemd credential. |
| `OAUTH2_TOKEN_CACHE_TTL` | `300` | Seconds a token-exchange result stays in Redis. |
| `REDIS_URL` | `redis://localhost:6387/0` | Redis used for the token-exchange cache. |

`OAUTH2_INTROSPECTION_CACHE_TTL`, `OAUTH2_TRUSTED_ISSUERS`, `JWKS_CACHE_TTL`
and `REDIS_KEY_PREFIX` are declared in the settings (with defaults `60`,
empty, `3600` and `knowledge`) but are not read by the code yet.

`compose.yml` now also starts a `redis:7-alpine` container published on port
`6387`, which matches the default `REDIS_URL`.

## Tests

pytest:

- `unit/test_auth_models.py`: claim mapping, scope wildcards and the
  `can_*` helpers of `User`.
- `unit/test_auth_jwt.py`: signature, issuer and expiry validation,
  introspection, userinfo and the validator singleton.
- `unit/test_auth_token_exchange.py`: exchange requests, Redis caching,
  failures and scope validation.
- `unit/test_auth_dependencies.py`: token extraction, `get_auth_context` with
  and without token exchange, tenant header and default-organization
  resolution, optional variants and `require_scopes`.
- `unit/test_config.py`: `oauth2_token_url`.
- `unit/test_main.py`: shutdown closes the auth clients even when they fail,
  and the Swagger OAuth2 configuration.

behave (`features/authentication.feature`): a throw-away FastAPI application
protected by `require_scopes("documents:read")` is called with tokens signed
by a local RSA key whose public half is served by a fake JWKS client.

- A request without a token is rejected
- A valid token carrying the required scope is accepted
- A token without the required scope is forbidden
- A wildcard scope grants every scope of its namespace
- An expired token is rejected
- A token signed by an unknown key is rejected
- The tenant header selects the tenant of the request
- A malformed tenant header is rejected
