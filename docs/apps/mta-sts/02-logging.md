# Dual-stream logging

Logging is configured when `mta_sts.main` is imported, from the `LOG_LEVEL`
setting. Records are split over two streams so that systemd can capture them
in separate files.

## What it does

`mta_sts.logging.setup_logging(level)` configures the root logger:

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

`mta_sts.logging.get_logger(name)` returns a standard logger, typically
called with `__name__`.

## Settings

| Variable | Default | Description |
| --- | --- | --- |
| `LOG_LEVEL` | `INFO` | Minimum level: `DEBUG`, `INFO`, `WARNING`, `ERROR` or `CRITICAL` |

## How it is tested

Pytest (`apps/mta-sts/tests/`):

- `test_logging.py` - both filters, handler layout, level selection and
  fallback, noise reduction of third-party loggers and `get_logger`.
- `test_main.py` - importing the application calls `setup_logging` with the
  configured level.

Behave (`apps/mta-sts/features/logging.feature`), with stdout and stderr
replaced by in-memory streams:

- Informational records go to stdout
- Warnings and errors go to stderr
- Records below the configured level are dropped
