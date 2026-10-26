# Dual-stream logging

Logging is configured when the application starts (the FastAPI lifespan
handler), from the `LOG_LEVEL` setting. Records are split over two streams so
that systemd can capture them in separate files.

## What it does

`webhooks.logging.setup_logging(level)` configures the root logger:

| Stream | Levels | Typical systemd target |
| --- | --- | --- |
| stdout | `DEBUG`, `INFO` | `StandardOutput` (output log) |
| stderr | `WARNING`, `ERROR`, `CRITICAL` | `StandardError` (error log) |

The split is implemented by two filters, `StdoutFilter` (records at or below
`INFO`) and `StderrFilter` (records at or above `WARNING`). Both handlers use
the format `%(asctime)s - %(name)s - %(levelname)s - %(message)s`. Existing
root handlers are replaced, and the `urllib3`, `httpx` and `httpcore`
loggers are lowered to `WARNING` to reduce noise. An unknown level name falls
back to `INFO`.

`webhooks.logging.get_logger(name)` returns a standard logger, typically
called with `__name__`.

## Application lifespan

`webhooks.main.lifespan` is an ASGI lifespan handler. On startup it calls
`setup_logging(level=settings.log_level)` and logs `Webhooks service
starting`; on shutdown it logs `Webhooks service shutting down`. Both
records are informational and therefore go to stdout.

## Settings

| Variable | Default | Description |
| --- | --- | --- |
| `LOG_LEVEL` | `INFO` | Minimum level: `DEBUG`, `INFO`, `WARNING`, `ERROR` or `CRITICAL` |

## Data model

None.

## How it is tested

Pytest:

- `test_logging.py` - both filters for every level, `setup_logging` (level,
  two handlers, replaced handlers, invalid level, third-party loggers) and
  `get_logger`.
- `test_main.py` (`TestLifespan`) - the lifespan configures logging with the
  configured level and logs the start and stop messages.

Behave (`apps/webhooks/features/logging.feature`), with the standard streams
replaced by in-memory buffers:

- Informational records go to stdout
- Warnings and errors go to stderr
- Records below the configured level are dropped
- The lifespan logs service start and stop on stdout

```bash
uv run --package webhooks pytest apps/webhooks
uv run --package webhooks behave apps/webhooks/features
```
