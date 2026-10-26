# Logging

Logging is configured once, when `frontend.main` is imported, by
`frontend.logging.setup_logging(level)`. It splits the records over the two
standard streams so that systemd can capture them in separate files:

| Stream | Records |
|--------|---------|
| standard output | `DEBUG` and `INFO` |
| standard error | `WARNING`, `ERROR` and `CRITICAL` |

Each handler has a filter that enforces the split, so a record is never
written twice. The root logger is reset on every call (existing handlers are
removed), and the `urllib3`, `httpx` and `httpcore` loggers are raised to
`WARNING` to keep third-party noise out of the logs.

## Log format

```text
2026-01-01 12:00:00 | INFO     | user=- | client=- | frontend.main | Health check requested
```

`user` and `client` come from a context variable. `set_request_context`
(user id, OAuth2 client id, extra keys) fills it, `clear_request_context`
empties it, and both default to `-`. `log_action(logger, action, ...)` writes
an `ACTION: <action> | key=value` line and sets the context when a user or
client is given. The helpers are available for later features; the application
currently logs the start of the application and each health check.

## Settings

| Variable | Default | Description |
|----------|---------|-------------|
| `LOG_LEVEL` | `INFO` | Minimum level (`DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL`); an unknown value falls back to `INFO` |

## Tests

pytest (`tests/test_logging.py`) checks the two filters, the context filter,
the stream split with captured output, the level handling and fallback, the
handler reset, the quieted libraries, `log_action` and the health-check log
record.

behave (`features/logging.feature`, steps in `features/steps/logging_steps.py`):

- Informational and warning records use different streams
- Records below the configured level are dropped
- Request context is part of every log line
- A health check leaves a log record

The steps replace `sys.stdout` and `sys.stderr` with in-memory buffers before
configuring logging and restore the root logger after each scenario.
