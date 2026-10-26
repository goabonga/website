# Token introspection

JWTs are checked against the auth server so that revoked tokens are refused,
and opaque tokens (personal access tokens) become usable. The results are
cached in Redis when it is configured.

## What it does

`IntrospectionClient` (`reachy_mini_api.auth.introspection`, global instance
`introspection_client`) implements OAuth2 Token Introspection (RFC 7662)
against `<issuer>/oauth2/introspect`, authenticating with the confidential
client (`OAUTH2_CLIENT_ID` and `OAUTH2_CLIENT_SECRET`).

- A token that looks like a JWT (three non-empty dot-separated segments) is
  validated by the [JWKS manager](03-jwt-auth.md) first, then introspected.
  If the server answers `active: false` the request fails with 401
  `Token has been revoked`.
- Any other token is treated as opaque: it can only be validated by
  introspection. An inactive token gives 401 `Token has been revoked`, a
  failing introspection call gives 401 `Invalid token`. The claims of the
  introspection response (`sub`, `scope`, `client_id`...) become the user.
- `get_auth_context` and `require_scopes` use this client, so every protected
  route (reports, status) accepts both kinds of token. The client id placed
  in the logging context falls back to `OAUTH2_CLIENT_ID` when the token has
  neither `client_id` nor `azp`.
- Introspection is skipped (the JWT is trusted after its signature check)
  when the client id, the client secret or the issuer is missing.
- For a JWT the check fails open: when the introspection request fails, the
  token is considered active and a warning is logged. For an opaque token a
  failure rejects the request, since nothing else can validate it.
- With `REDIS_URL` set, the activity of a JWT is cached for
  `TOKEN_INTROSPECTION_CACHE_TTL` seconds under
  `<REDIS_KEY_PREFIX>:introspect:<first 16 hex digits of the SHA-256 of the token>`
  (`1` active, `0` inactive). Opaque tokens are introspected on every
  request: their result is written to the cache but never read back. Redis
  errors are logged and ignored, the cache is optional.
- The lifespan hook closes the HTTP and Redis clients on shutdown.

## Settings

| Variable | Default | Description |
| --- | --- | --- |
| `OAUTH2_CLIENT_ID` | empty | Confidential client used to call the introspection endpoint |
| `OAUTH2_CLIENT_SECRET` | empty | Its secret, read from the systemd credential of the same name when `CREDENTIALS_DIRECTORY` is set, otherwise from the environment |
| `REDIS_URL` | empty | Redis URL of the cache (for example `unix:///run/redis/redis.sock?db=6`); caching is off when empty |
| `REDIS_KEY_PREFIX` | `reachy` | Prefix of the cache keys |
| `TOKEN_INTROSPECTION_CACHE_TTL` | `60` | Cache lifetime in seconds |

The Redis URL is read from `REDIS_URL` only: a variable named
`OAUTH2_CLIENT_REDIS_URL` is not read by the code.

## Data model

None. The cache entries are plain `"1"` / `"0"` strings with a TTL.

## How it is tested

Pytest:

- `test_auth_introspection.py` - properties, HTTP and Redis clients, cache
  keys, cache read and write errors, `introspect_token` (cache hit, active,
  inactive, fail open), opaque token validation and `close`.
- `test_auth_dependencies_introspection.py` - JWT detection, JWT and opaque
  paths of `get_auth_context` and `require_scopes`, revoked and invalid
  tokens, client id fallback.
- `test_config.py` and `test_main.py` - new settings, `get_credential` and
  the lifespan shutdown.

Behave (`apps/reachy-mini-api/features/introspection.feature`), with the
introspection endpoint and Redis replaced by in-process fakes:

- An active opaque token is accepted
- An inactive opaque token is rejected
- An opaque token without the scope is forbidden
- A revoked JWT is rejected
- A JWT stays valid when the introspection endpoint is unreachable
- The introspection result is cached
