# Anonymous sessions

Visitors without an account are identified by a session id kept in a cookie.
The session is stored in PostgreSQL and mirrored in Redis, and the
`get_chat_context` dependency turns "who is calling" into a single
`ChatContext` that later features use to attach conversations to an owner.

## Data model

| Table | Model | Columns |
|-------|-------|---------|
| `anonymous_sessions` | `AnonymousSession` | `id` (UUID), `session_id` (36 characters, unique, indexed), `created_at`, `last_active` |

## SessionService

`SessionService(db)` keeps one record per session id.

| Method | Behaviour |
|--------|-----------|
| `get(session_id)` | Read `anon:session:<id>` in Redis and refresh its TTL; on a miss read PostgreSQL and re-cache; `None` if unknown |
| `create(session_id)` | Validate the UUID format (`ValueError` otherwise), insert, cache |
| `get_or_create(session_id)` | `get` then `create` |
| `delete(session_id)` | Remove from PostgreSQL and Redis; returns whether a row existed |
| `close()` | Close the Redis connection |

## ChatContext

`get_chat_context` resolves the caller in this order:

1. A valid bearer token (`_get_optional_user`, which never raises). The
   context is authenticated, carries the user scopes and the access token,
   and exposes a valid session cookie as `anonymous_session_id` so that its
   conversation can be migrated later.
2. A `session_id` cookie containing a UUID and known to `SessionService`:
   the existing session is reused.
3. A well-formed but unknown session id: the session creation budget is
   checked, then the id is registered (`session_created=True`).
4. Nothing usable (no cookie, or a malformed value): a new UUID session is
   created, again within the creation budget.

When the budget of the rate limiter (see the rate limiting page) is
exhausted the dependency answers `429 Session creation limit exceeded` with a
`Retry-After` header. `ChatContext.owner_id` is the user id when
authenticated and the session id otherwise. `require_session_or_auth`
answers `401` when the context has neither.

The context also carries `client_ip`, the access token and the scope set;
the HTTP layer that sets the cookie is part of the chat endpoint feature.

## Settings

| Variable | Default | Description |
|----------|---------|-------------|
| `SESSION_REDIS_URL` | `redis://localhost:6379/2` | Redis database holding session records |
| `SESSION_REDIS_TTL` | `3600` | Seconds a cached session lives; refreshed on access |

## Tests

- pytest: `tests/session/test_service.py`, `tests/session/test_dependencies.py`
  and `tests/models/test_session.py`.
- behave: `features/session.feature` ("A first visit creates a session", "A
  known session cookie is reused", "An unknown session id is registered", "A
  malformed cookie is ignored", "Session creation is rate limited", "An
  authenticated user takes priority over the cookie"). The scenarios mount
  `get_chat_context` on a small application and replace the session service,
  the database and the rate limiter with fakes.
