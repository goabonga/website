# JWT authentication

Bearer tokens are validated against the signing keys published by an OpenID
Connect issuer, and routes declare the scopes they need.

## What it does

- `JWKSManager` (`reachy_mini_api.auth.jwks`, global instance
  `jwks_manager`) discovers the issuer configuration at
  `<issuer>/.well-known/openid-configuration`, caches it for `JWKS_CACHE_TTL`
  seconds and resolves the signing key of a token through `PyJWKClient`.
  Tokens must be signed with `RS256` or `ES256`; the signature, `exp`, `iat`
  and `iss` are verified. The audience is not checked.
- The accepted issuers are the primary issuer (`OAUTH2_ISSUER`) plus the
  comma-separated `OAUTH2_TRUSTED_ISSUERS`.
- `User` (`reachy_mini_api.auth.models`) is built from the token claims. The
  scopes come from the `scope` claim (space-separated string) or `scp`
  (list). A token whose `client_id` equals its `sub`, or whose `sub` is not a
  UUID, is flagged as a machine client (client credentials). Scope matching
  supports wildcards: `*` matches everything and `resource:*` matches every
  scope starting with `resource:`.
- `require_scopes("a:read", ...)` is a FastAPI dependency factory. It
  answers:
    - 401 with `WWW-Authenticate: Bearer` when no token is sent,
    - 503 when `OAUTH2_ISSUER` is not set,
    - 401 `Invalid token` when the token cannot be validated (bad signature,
      expired, unknown issuer, no `sub` claim),
    - 403 `Insufficient scopes. Missing: ...` when a required scope is absent,
    - otherwise an `AuthContext` (`user`, `user_id`, `scopes`, `has_scope`,
      `require_scope`).
- `get_auth_context` / `Auth` and `get_current_user` / `CurrentUser` provide
  the same validation without scope requirements.
- The identity (`user_id`, `client_id`) is stored in the logging context and
  on `request.state`, so the request logging middleware prints it. The client
  id comes from the `client_id` claim, then `azp`.
- When `OAUTH2_ISSUER` is set, the token is read through an
  `OAuth2AuthorizationCodeBearer` scheme (authorization and token URLs under
  `<issuer>/oauth2/`), which makes Swagger UI show an "Authorize" button;
  otherwise the `Authorization: Bearer` header is read directly. The scheme
  is built when the module is imported, so the issuer must be set in the
  environment before the application starts.
- When both `OAUTH2_ISSUER` and `OAUTH2_SWAGGER_CLIENT_ID` are set, Swagger UI
  is configured for the authorization code flow with PKCE and persists the
  authorization.
- The lifespan hook closes the HTTP client of the JWKS manager on shutdown.

No route uses these dependencies yet: the following features declare the
scopes of their endpoints.

## Settings

| Variable | Default | Description |
| --- | --- | --- |
| `OAUTH2_ISSUER` | empty | OIDC issuer URL; routes answer 503 while it is empty |
| `OAUTH2_SWAGGER_CLIENT_ID` | empty | Public PKCE client used by Swagger UI |
| `OAUTH2_TRUSTED_ISSUERS` | empty | Additional trusted issuers, comma-separated |
| `JWKS_CACHE_TTL` | `3600` | Cache lifetime of the discovery document and of the keys, in seconds |

## Data model

None. Keys and the discovery document are cached in memory.

## How it is tested

Pytest:

- `test_auth_models.py` - claims parsing, machine clients and scope matching.
- `test_auth_jwks.py` - issuers, discovery caching, key resolution and token
  validation errors.
- `test_auth_dependencies.py` - bearer extraction, the OAuth2 scheme,
  `AuthContext`, `get_auth_context`, `require_scopes` (401, 403, 503,
  wildcards) and a protected route served by `TestClient`.
- `test_main.py` and `test_config.py` - Swagger configuration, the lifespan
  hook and the new settings.

Behave (`apps/reachy-mini-api/features/jwt_auth.feature`). The scenarios
sign real RS256 tokens with a throw-away key and replace only the network
calls of the JWKS manager, so the whole validation runs in-process:

- A request without token is rejected
- A valid token carrying the scope is accepted
- A valid token without the scope is forbidden
- A wildcard scope grants access
- An expired token is rejected
- A token from an unknown issuer is rejected
- A token from a trusted additional issuer is accepted
