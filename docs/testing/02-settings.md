# Settings

How browser scenarios run is configured by `E2E_*` environment variables.
`e2e_support.settings.E2ESettings.from_env()` reads them once and returns an
immutable dataclass; nothing is hard-coded in the scenarios.

## Variables

| Variable | Default | Description |
| --- | --- | --- |
| `E2E_BROWSER` | `chromium` | Engine to launch: `chromium`, `firefox` or `webkit` |
| `E2E_HEADLESS` | `true` | Run without a visible window; set `0` to watch the run |
| `E2E_SLOWMO` | `0` | Milliseconds Playwright waits between actions, to follow a run by eye |
| `E2E_ARTIFACTS_DIR` | `artifacts` | Directory receiving the files saved for failed scenarios (relative to the working directory) |
| `E2E_SKIP_BROWSER` | `false` | Skip every `@browser` scenario and start no browser |
| `E2E_TIMEOUT` | `10000` | Default timeout of Playwright actions and expectations, in milliseconds |
| `E2E_TRACE` | `true` | Record a Playwright trace and keep it when the scenario fails |

Booleans accept `1`/`0`, `true`/`false`, `yes`/`no` and `on`/`off`, in any
case. A blank `E2E_ARTIFACTS_DIR` falls back to the default.

## Errors

An unusable value raises `SettingsError` (a `ValueError`) naming the
variable, for example `E2E_BROWSER='netscape' is not supported (choose one of
chromium, firefox, webkit)`. Misconfiguration therefore fails the run
immediately instead of producing a confusing browser error later.

## Usage

```python
from e2e_support.settings import E2ESettings

settings = E2ESettings.from_env()  # reads os.environ
settings = E2ESettings.from_env({"E2E_HEADLESS": "0"})  # explicit mapping
```

## How it is tested

Pytest (`libs/e2e-support/tests/test_settings.py`): defaults, every
variable, the process environment as default source, boolean spellings, a
blank artifacts directory and the rejection of invalid values.
