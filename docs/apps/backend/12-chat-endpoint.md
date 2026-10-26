# Chat endpoint

The public HTTP face of the service: one route, `POST /api/v1/chat`, that
either streams an answer as Server-Sent Events or returns the conversation
history, for authenticated users and anonymous visitors alike.

## Endpoint

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/v1/chat` | POST | Send `{"message": "..."}`; the answer is an SSE stream |
| `/api/v1/chat?history=true` | POST | Return `{"messages": [...], "session_id": ...}` as JSON and ignore the message |

The body is validated by `ChatRequest`; a missing `message` gives `422`.

### Who is calling

The route depends on `check_rate_limit_with_context`
(`backend.middleware.dependencies`), which builds the `ChatContext` of the
session feature and then applies the request rate limit:

- `Authorization: Bearer <token>` identifies a user (JWT or opaque token);
  the rate limit is the authenticated one.
- Otherwise the `session_id` cookie identifies an anonymous session, which is
  created on the first request.
- When the limit is exceeded the answer is `429` with `Retry-After`,
  `X-RateLimit-Remaining: 0` and `X-RateLimit-Reset` headers.

`check_rate_limit` is the lighter variant that only returns the optional
user. `backend.middleware` exposes both, and the limiter itself, lazily.

### Streaming response

The response has the media type `text/event-stream` and the headers
`Cache-Control: no-cache`, `Connection: keep-alive` and
`X-Accel-Buffering: no`, so a reverse proxy does not buffer it. It is the
event stream of the orchestration page: `intent`, `tools` (when a tool ran),
`token` events, then `done` with the `conversation_id` and token usage, or
`error`.

### Cookie and migration

- For a newly created session the route sets an `httpOnly` cookie named
  `SESSION_COOKIE_NAME`, in both modes.
- If an authenticated caller still carries an anonymous session cookie, the
  anonymous conversation is moved to the user (`ChatService.migrate_conversation`),
  the cached copy is invalidated, the anonymous session is deleted and the
  cookie is cleared in the response.

## Settings

| Variable | Default | Description |
|----------|---------|-------------|
| `SESSION_COOKIE_NAME` | `session_id` | Name of the cookie written by the route |
| `SESSION_COOKIE_MAX_AGE` | `2592000` | Cookie lifetime in seconds (30 days) |
| `SESSION_COOKIE_SECURE` | `true` | Send the cookie over HTTPS only; set `false` for local HTTP |
| `SESSION_COOKIE_SAMESITE` | `lax` | `strict`, `lax` or `none` |
| `SESSION_COOKIE_DOMAIN` | empty | Cookie domain; empty means the current host |

The cookie that is read is always called `session_id`
(`get_chat_context`), so changing `SESSION_COOKIE_NAME` also needs the
reading side to be changed.

## Application wiring

`backend.main` includes the router and its OpenAPI description now lists the
chat, RAG, session, rate limiting and OAuth2 features. With
`DOCS_ENABLED=true` Swagger UI exposes the route.

## Tests

- pytest: `tests/routes/test_chat.py` (history mode, streaming mode, cookies,
  migration, validation), `tests/middleware/test_dependencies.py`,
  `tests/test_middleware_init.py` and the cookie defaults in
  `tests/test_config.py`. `tests/conftest.py` gains the `auth_client` and
  `admin_client` fixtures.
- behave: `features/chat.feature` (history for anonymous and authenticated
  users, SSE streams and their headers, session cookie, request validation
  and rate limiting). The scenarios call the real application with a mocked
  database, a fake orchestrator and overridden dependencies.
