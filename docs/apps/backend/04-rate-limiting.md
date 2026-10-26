# Redis rate limiting

A sliding-window limiter backed by Redis sorted sets. It limits ordinary
requests per user or per client address, and keeps a separate, much
stricter budget for the creation of new anonymous sessions.

## Modules

| Module | Role |
|--------|------|
| `backend.middleware.rate_limit` | `RateLimiter` and the `get_rate_limiter` accessor (one shared instance) |
| `backend.utils.request` | `get_client_ip(request)` |
| `backend.middleware` | Lazy re-exports of the limiter, to avoid circular imports with later features |

## How it works

`RateLimiter.check_rate_limit(user_id, client_ip)` returns a tuple
`(allowed, remaining, reset_seconds)`.

- An authenticated caller is counted under `ratelimit:user:<id>` with the
  authenticated limit; an anonymous caller under `ratelimit:ip:<ip>` with
  the anonymous limit.
- In one Redis pipeline the limiter removes the members older than the
  window, counts the remaining ones, adds the current request (the score and
  member are the timestamp) and refreshes the key expiry.
- When the count was already at the limit, the request just added is
  removed again and `(False, 0, window)` is returned. Otherwise the result is
  `(True, limit - count - 1, window)`.

Session creation uses its own keys, `ratelimit:session_create:<ip>`.
`check_session_creation_limit(ip)` only reads the count, and
`record_session_creation(ip)` adds an entry; the caller records a creation
only once it really happened.

The Redis client is created lazily from `RATE_LIMIT_REDIS_URL` and closed
with `RateLimiter.close()`.

## Client address

`get_client_ip` returns, in order, the first entry of `X-Forwarded-For`,
the `X-Real-IP` header, the socket peer address and finally `"unknown"`.
These headers are trusted as sent, so the service must only be reachable
through the reverse proxy that sets them.

## Settings

| Variable | Default | Description |
|----------|---------|-------------|
| `RATE_LIMIT_REDIS_URL` | `redis://localhost:6379/1` | Redis database used by the limiter |
| `RATE_LIMIT_ANON` | `10` | Requests per window for an anonymous caller |
| `RATE_LIMIT_AUTH` | `60` | Requests per window for an authenticated user |
| `RATE_LIMIT_WINDOW` | `60` | Window size in seconds |
| `SESSION_CREATE_LIMIT` | `3` | New sessions allowed per address and window |
| `SESSION_CREATE_WINDOW` | `86400` | Session creation window in seconds |

## Tests

- pytest: `tests/middleware/test_rate_limit.py`, `tests/utils/test_request.py`,
  `tests/test_middleware_init.py` and the defaults in `tests/test_config.py`.
- behave: `features/rate_limit.feature` ("Anonymous requests are allowed
  until the limit is reached", "Limits are tracked per client address",
  "Authenticated users get a higher limit", "Remaining quota is reported",
  "Session creation is limited per address", "Client address honours proxy
  headers"). The scenarios replace Redis with an in-memory sorted-set fake
  defined in the steps.
