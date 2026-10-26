# Dual-stream logging

Structured logging that splits the output in two streams, and a middleware
that logs every HTTP request with its timing and user context.

## What it does

- `setup_logging(level)` configures the root logger with two handlers:
  `DEBUG` and `INFO` records go to stdout, `WARNING`, `ERROR` and `CRITICAL`
  records go to stderr. Under systemd each stream is captured in its own
  file (`output.log` and `error.log`).
- Every record carries the request context in its format:
  `<time> | <LEVEL> | user=<id> | client=<id> | <logger> | <message>`.
  The context is stored in a `ContextVar` and defaults to `-`.
- `log_action(logger, action, **details)` writes an `ACTION: <action> | k=v`
  line, used by the API features to audit each call.
- `urllib3`, `httpx` and `httpcore` are lowered to `WARNING` to reduce noise.
- `RequestLoggingMiddleware` assigns an 8 character request id
  (`request.state.request_id`), logs `REQUEST: <method> <path>`, then
  `RESPONSE: <method> <path> | status=<code> | duration=<ms>ms`, or
  `ERROR: ...` followed by a re-raise when the handler fails. When a later
  feature stores `user_id` and `client_id` on `request.state`, they are added
  to the context. The context is always cleared at the end of the request.
- The application lifespan calls `setup_logging(settings.log_level)` on
  startup and logs the start and the shutdown.

## Settings

| Variable | Default | Description |
| --- | --- | --- |
| `LOG_LEVEL` | `INFO` | Minimum level: `DEBUG`, `INFO`, `WARNING`, `ERROR` or `CRITICAL` (an unknown value falls back to `INFO`) |

## Data model

None.

## How it is tested

Pytest:

- `test_logging.py` - the three filters, `setup_logging` handlers and levels,
  context helpers and `log_action`.
- `test_middleware.py` - success, request id, user context, request and
  response log lines, exceptions and context clearing.
- `test_main.py` - the lifespan hook and the middleware registration.
- `test_config.py` - the `LOG_LEVEL` setting.

Behave (`apps/reachy-mini-api/features/logging.feature`), with stdout and
stderr captured in memory:

- Informational records go to stdout
- Warnings and errors go to stderr
- Records below the configured level are dropped
- Every HTTP request is logged with its outcome
