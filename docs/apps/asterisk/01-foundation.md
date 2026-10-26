# Application foundation

The foundation provides the installable package, the settings object and
the logging setup. The entry point does not serve calls yet: it only
reports the effective configuration. The following features add the
AudioSocket server, the audio conversion, the OpenAI client and the call
handler on top of it.

## What it does

- Defines the `asterisk` package (`asterisk.__version__`, currently
  `0.0.0`, managed by the release tooling).
- Reads the settings from environment variables into a `Config` object,
  exposed as the module-level singleton `asterisk.config.config`. A `.env`
  file is loaded first when present (`python-dotenv`).
- Configures logging: records below `ERROR` go to stdout, records at
  `ERROR` and above go to stderr, with a common timestamped format.
- `python -m asterisk.main` configures logging and calls
  `log_configuration()`, which logs the AudioSocket address the process is
  configured for.

## Settings

| Variable | Default | Description |
| --- | --- | --- |
| `AUDIOSOCKET_HOST` | `127.0.0.1` | Bind address of the AudioSocket server |
| `AUDIOSOCKET_PORT` | `9092` | TCP port of the AudioSocket server |
| `LOG_LEVEL` | `INFO` | Python logging level name |

Settings are read once, when `asterisk.config` is imported.

## Data model

None. The application has no database at this stage.

## Running it

```bash
uv sync --package asterisk
uv run --package asterisk python -m asterisk.main
```

## Tests

- pytest: `tests/test_config.py` (defaults, environment overrides, port
  type, singleton) and `tests/test_main.py` (stdout/stderr logging split,
  `log_configuration`).
- behave: `features/foundation.feature` with the scenarios *Default
  settings*, *Settings overridden by the environment*, *Logging is split
  between stdout and stderr* and *The effective configuration is logged*.
