# OAuth2 authentication

Every API endpoint added by the following features is protected by bearer
tokens issued by the platform's OAuth2 / OIDC server. This feature adds the
`custom_domain.auth` package that validates those tokens and checks scopes,
and wires its clients into the application lifespan.

No public endpoint is added here: the dependencies are consumed by the routes
of the next features.

## How a request is authenticated

1. The token is read from the `Authorization: Bearer ...` header. When
   `OAUTH2_ISSUER` is set the dependency is an `OAuth2AuthorizationCodeBearer`
   scheme (so Swagger UI can log in with PKCE); otherwise the header is parsed
   directly. A missing token answers `401`.
2. If `OAUTH2_ISSUER` is empty the service answers `503 OAuth2 not configured`.
3. A token made of three dot-separated segments is treated as a JWT:
   - the signature is verified against the issuer's JWKS, discovered through
     `<issuer>/.well-known/openid-configuration` (algorithms `RS256` and
     `ES256`, issuer must be the primary issuer or one of
     `OAUTH2_TRUSTED_ISSUERS`, `exp` and `iat` are checked, the audience is
     not);
   - the token is then checked against the introspection endpoint
     (`<issuer>/oauth2/introspect`, RFC 7662). The result is cached in Redis
     for `TOKEN_INTROSPECTION_CACHE_TTL` seconds. Introspection needs
     `OAUTH2_CLIENT_ID` and `OAUTH2_CLIENT_SECRET`; when it is not configured,
     or when the introspection request fails, the token is accepted (the
     check fails open and logs a warning).
4. Any other token is an opaque token (for example a personal access token).
   It is validated by introspection only, and an inactive token answers `401
   Token has been revoked`.
5. The claims become a `User`. Scopes come from the `scope` (space separated)
   or `scp` claim. A token whose `client_id` claim equals its `sub`, or whose
   `sub` is not a UUID, is flagged `is_machine_client`.

## Scope checks

`require_scopes(*scopes)` returns a FastAPI dependency that yields an
`AuthContext` (with `user`, `user_id`, `scopes`, `has_scope()` and
`require_scope()`):

- For a JWT, when token exchange is configured (`OAUTH2_ISSUER`,
  `OAUTH2_CLIENT_ID` and `OAUTH2_CLIENT_SECRET` all set), the token is
  exchanged at the issuer's token endpoint (RFC 8693) asking for the required
  scopes. The scopes granted by the exchange replace the token's own scopes.
  `invalid_grant` answers `401`, `insufficient_scope` answers `403`. Exchange
  results are cached in Redis for `OAUTH2_CLIENT_CACHE_TTL` seconds.
- Otherwise (opaque token, or token exchange not configured) the scopes found
  in the token are compared with the required ones; missing scopes answer
  `403 Insufficient scopes`.
- Wildcards are honoured: a `*` scope matches everything and `resource:*`
  matches every scope starting with `resource:`.

`get_auth_context` / `get_current_user` (and the `Auth` / `CurrentUser` type
aliases) authenticate without requiring any scope.

After a successful check the user and client identifiers are stored on
`request.state` and in the logging context (`set_request_context`).

The scopes the service uses are `custom-domain:read`, `custom-domain:write`,
`custom-domain:lookup` and the administration scope (plus its `:clients`,
`:templates` and `:stats` sub-scopes for the admin features). The administration
scope is a setting (`ADMIN_SCOPE`); `AuthContext.is_admin` tells whether the
caller holds it, and the feature pages use it to let an operator cross client
boundaries. The scopes are described in the OpenAPI description served when
`DOCS_ENABLED=true`.

## Settings

| Variable | Default | Description |
| --- | --- | --- |
| `REDIS_URL` | `redis://localhost:6379/13` | Redis used for the introspection and token-exchange caches. |
| `REDIS_KEY_PREFIX` | `custom-domain` | Prefix of the cache keys (`<prefix>:introspect:*`, `<prefix>:tex:*`). |
| `OAUTH2_ISSUER` | empty | Issuer of the tokens, for example `https://auth.example.com`. Empty disables authentication (every protected call answers `503`), so a deployment must set it. |
| `ADMIN_SCOPE` | `custom-domain:admin` | Scope that marks an operator. Its `:clients`, `:templates` and `:stats` variants guard the matching admin API. |
| `OAUTH2_SWAGGER_CLIENT_ID` | empty | Public client used by Swagger UI (PKCE). |
| `OAUTH2_CLIENT_ID` | empty | Confidential client used for introspection and token exchange. |
| `OAUTH2_CLIENT_SECRET` | empty | Secret of that client. Read from the systemd credential of the same name (`CREDENTIALS_DIRECTORY`) first, then from the environment. |
| `OAUTH2_TRUSTED_ISSUERS` | empty | Comma-separated extra issuers accepted in tokens. |
| `OAUTH2_HTTP_TIMEOUT_SECONDS` | `10.0` | Timeout of the HTTP calls to the OAuth2 server (discovery, keys, introspection, token exchange). |
| `OAUTH2_CLIENT_CACHE_TTL` | `300` | Lifetime in seconds of cached token-exchange results. |
| `TOKEN_INTROSPECTION_CACHE_TTL` | `60` | Lifetime in seconds of cached introspection results. |
| `JWKS_CACHE_TTL` | `3600` | Lifetime in seconds of the cached discovery document and signing keys. |

`TOKEN_VALIDATION_MODE`, `TOKEN_EXCHANGE_CACHE_TTL`,
`OAUTH2_INTROSPECTION_ENDPOINT`, `OAUTH2_TOKEN_ENDPOINT` and `OAUTH2_JWKS_URI`
are declared in the settings but no code reads them: the validation flow
described above is fixed and the endpoints are always discovered from the
issuer.

## Lifespan

On shutdown the application closes the JWKS, token-exchange and introspection
HTTP and Redis clients before disposing the database engine.

## How it is tested

- pytest: `test_auth_models.py` (claims to `User`, machine clients, wildcard
  scopes), `test_auth_jwks.py`, `test_auth_introspection.py`,
  `test_auth_token_exchange.py` and `test_auth_dependencies.py` (every
  response code of the dependencies), plus the credential and enum tests of
  `test_config.py`. The conftest gains the user fixtures and authenticated
  HTTP clients.
- behave: `features/authentication.feature` exercises `require_scopes` through
  a probe endpoint with a fake auth server: *A request without a token is
  rejected*, *A token carrying the required scope is accepted*, *A token
  without the required scope is rejected*, *A wildcard scope grants access*,
  *A revoked token is rejected* and *A machine token is recognised by its
  client_id subject*. The shared steps `I am authenticated as client ... with
  scopes ...` are reused by the later features.
