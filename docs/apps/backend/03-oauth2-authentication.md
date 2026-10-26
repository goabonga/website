# OAuth2 token authentication

Validates bearer tokens issued by the platform's `auth` application and
exposes FastAPI dependencies to protect routes. The `backend` service is a
resource server: it never issues tokens.

## Modules

| Module | Role |
|--------|------|
| `backend.auth.jwks` | `JWKSManager`: OIDC discovery, JWKS caching and JWT signature check |
| `backend.auth.introspection` | `IntrospectionClient`: RFC 7662 revocation check with a Redis cache |
| `backend.auth.token_exchange` | `TokenExchangeClient`: RFC 8693 exchange used to confirm granted scopes |
| `backend.auth.models` | `User`, built from token claims, with scope helpers |
| `backend.auth.dependencies` | `oauth2_scheme`, `get_auth_context`, `get_current_user`, `require_scopes` |

## Validation flow

1. The token comes from the `Authorization: Bearer` header. When
   `OAUTH2_ISSUER` is set, the OAuth2 authorization-code scheme is used so
   that Swagger UI can log in with PKCE; otherwise the header is parsed by
   hand.
2. A missing token gives `401 Missing authorization token`. If the issuer is
   not configured the dependency answers `503 OAuth2 not configured`.
3. A token with three non-empty dot-separated segments is treated as a JWT:
   `JWKSManager.validate_token` downloads
   `<issuer>/.well-known/openid-configuration`, resolves `jwks_uri`, verifies
   the signature (RS256 or ES256), `exp`, `iat` and `iss`, then
   `IntrospectionClient` asks the auth server whether the token is still
   active. The audience is not verified.
4. Any other token is an opaque token (for example a personal access token)
   and is validated by introspection only.
5. A revoked token gives `401 Token has been revoked`; any other failure
   gives `401 Invalid token`, both with a `WWW-Authenticate` header.

Introspection is fail-open: when the introspection endpoint cannot be
reached, or introspection is not configured, a JWT with a valid signature is
accepted and a warning is logged. Opaque tokens have no such fallback and are
rejected.

## The `User` model

`User.from_jwt_claims` reads `sub`, `email`, `name` (or
`preferred_username`) and the scopes from `scope` (space separated) or
`scp` (list). A token is a machine token when `client_id` equals `sub` or
when `sub` is not a UUID. `has_scope` supports the `*` wildcard and prefix
wildcards such as `api:*`; `has_any_scope` and `has_all_scopes` combine
them.

## Dependencies

- `get_current_user` (alias `CurrentUser`) returns the `User`.
- `get_auth_context` (alias `Auth`) returns an `AuthContext` with
  `user_id`, `scopes`, `has_scope` and `require_scope`, and sets the logging
  request context.
- `require_scopes("a", "b")` builds a dependency that enforces scopes. For a
  JWT with token exchange configured, the exchange response decides
  (`401` for `invalid_grant`, `403` for `insufficient_scope`); otherwise the
  scopes of the validated token are checked locally. Missing scopes answer
  `403 Insufficient scopes` with an `insufficient_scope` challenge.

```python
@router.get("/resource")
async def read_resource(auth: AuthContext = Depends(require_scopes("api:read"))):
    return {"user": auth.user_id}
```

## Application hooks

`backend.main` closes the three HTTP/Redis clients in the lifespan shutdown,
and `get_swagger_ui_oauth2_config` enables the PKCE flow in Swagger UI when
`OAUTH2_ISSUER` and `OAUTH2_SWAGGER_CLIENT_ID` are both set.

## Settings

| Variable | Default | Description |
|----------|---------|-------------|
| `OAUTH2_ISSUER` | empty | Issuer URL of the auth server; empty disables authentication |
| `OAUTH2_SWAGGER_CLIENT_ID` | empty | Public client used by Swagger UI |
| `OAUTH2_CLIENT_ID` | empty | Client id of this service for introspection and exchange |
| `OAUTH2_CLIENT_SECRET` | empty | Client secret, see below |
| `OAUTH2_TRUSTED_ISSUERS` | empty | Extra accepted issuers, comma separated |
| `OAUTH2_CLIENT_CACHE_TTL` | `300` | Seconds a token exchange result is cached |
| `TOKEN_INTROSPECTION_CACHE_TTL` | `60` | Seconds an introspection result is cached |
| `JWKS_CACHE_TTL` | `3600` | Seconds the discovery document and JWKS are cached |
| `REDIS_URL` | empty | Redis used for the caches; empty disables caching |
| `REDIS_KEY_PREFIX` | `fastapi` | Prefix of the cache keys |

`OAUTH2_CLIENT_SECRET` is read with `get_credential`: a file of that name in
`$CREDENTIALS_DIRECTORY` (systemd credentials) wins over the environment
variable, so the secret never has to appear in a unit file.

## Tests

- pytest: `tests/test_auth_models.py`, `test_auth_jwks.py`,
  `test_auth_introspection.py`, `test_auth_token_exchange.py`,
  `test_auth_dependencies.py`, plus the credential and OAuth2 default tests in
  `tests/test_config.py` and the Swagger tests in `tests/test_main.py`.
  `tests/conftest.py` provides the user and claims fixtures.
- behave: `features/auth.feature` ("Request without a token is rejected",
  "OAuth2 not configured returns service unavailable", "Valid JWT identifies
  the user", "Revoked token is rejected", "Missing scope is forbidden",
  "Wildcard scope grants access"). A small protected application is built in
  the steps and the JWKS, introspection and exchange clients are replaced by
  mocks, so no auth server is needed.
