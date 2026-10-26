# Token exchange

Instead of trusting the scopes written in the token, the service can ask the
auth server whether the user was granted the scopes a route requires, using
OAuth2 Token Exchange (RFC 8693). The answers are cached in Redis.

## What it does

`TokenExchangeClient` (`reachy_mini_api.auth.token_exchange`, global instance
`token_exchange_client`) posts to the `token_endpoint` found in the issuer
discovery document, with the grant type
`urn:ietf:params:oauth:grant-type:token-exchange`, the user token as
`subject_token`, the requested scopes as `scope` and the confidential client
credentials.

It is *configured* when `OAUTH2_CLIENT_ID`, `OAUTH2_CLIENT_SECRET` and
`OAUTH2_ISSUER` are all set. In `require_scopes(...)`:

- a **JWT** with at least one required scope goes through the exchange:
    - on success the granted scopes (`scope` of the answer) replace the scopes
      of the token. The claims come from the exchanged access token when it can
      be validated, otherwise the original token is validated (signature and
      [introspection](07-introspection.md)); if that fails the request gets
      401 `Token validation failed`.
    - `invalid_grant` gives 401 `Invalid or expired token`.
    - `insufficient_scope` gives 403 `Insufficient scopes. Required: ...`
      with a `WWW-Authenticate: Bearer error="insufficient_scope"` header.
    - any other error gives 401 with the error as detail.
- **opaque tokens**, routes without required scope, and deployments where the
  exchange is not configured use the direct validation of the previous
  features (scopes carried by the token, wildcards supported).

With `REDIS_URL` set, successful answers are cached for
`OAUTH2_CLIENT_CACHE_TTL` seconds under
`<REDIS_KEY_PREFIX>:tex:<token hash>:<scopes hash>`, so a token and a set of
scopes cost one exchange per period. Redis errors are logged and ignored.
The lifespan hook closes the HTTP and Redis clients on shutdown.

## Settings

| Variable | Default | Description |
| --- | --- | --- |
| `OAUTH2_CLIENT_CACHE_TTL` | `300` | Lifetime of a cached exchange answer, in seconds |

It also uses `OAUTH2_ISSUER`, `OAUTH2_CLIENT_ID`, `OAUTH2_CLIENT_SECRET`,
`REDIS_URL` and `REDIS_KEY_PREFIX` described in the previous pages. The
OAuth2 client must be registered on the auth server with the token exchange
grant.

## Data model

None. The cache entries are JSON documents with a TTL.

## How it is tested

Pytest:

- `test_auth_token_exchange.py` - error class, configuration, HTTP and Redis
  clients, cache keys and cache errors, `exchange_token` (cache hit, missing
  endpoint, request body, error answers, success), `validate_token_scopes`
  and `close`.
- `test_auth_dependencies_token_exchange.py` - the exchange path of
  `require_scopes` (claims from the exchange or from introspection, 401 and
  403 errors, request context) and the cases where the exchange is skipped.
- `test_config.py` and `test_main.py` - the new setting and the lifespan.

Behave (`apps/reachy-mini-api/features/token_exchange.feature`), with the
auth server and Redis replaced by in-process fakes while the real exchange
code runs:

- The auth server grants the required scope
- The auth server refuses the scope
- The auth server rejects the token
- The exchange result is cached
- Opaque tokens skip the exchange
