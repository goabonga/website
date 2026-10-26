# Browser session

`e2e_support.browser` wraps the Playwright sync API so that a whole run
shares one browser while every scenario gets its own isolated context.

## What it does

- `BrowserSession` starts the Playwright driver and launches the browser
  chosen by the [settings](02-settings.md) (engine, headless, slow motion).
  Starting a browser is slow, so a run creates the session once.
- `BrowserSession.new_scenario(name, base_url=None, **context_options)`
  opens a fresh `BrowserContext` with one page and returns a
  `BrowserScenario` exposing `context`, `page` and `base_url`. With a
  `base_url`, relative navigation such as `page.goto("/login")` works.
  Extra keyword arguments (`locale`, `viewport`, `storage_state`, ...) go to
  Playwright's `new_context`.
- A scenario never sees the cookies, local storage or permissions of
  another: isolation comes from the per-scenario context, not from clearing
  state.
- `E2E_TIMEOUT` is applied as the default timeout of actions and as the
  timeout of `expect(...)` assertions.
- `BrowserScenario.close()` closes the context and its pages.

## Browser not installed

Playwright drivers and browsers are separate downloads. When the browser
cannot be launched, `BrowserSession.start()` stops the driver and raises
`BrowserUnavailable` with an actionable message:

```text
the chromium browser is not installed (install it with: python -m playwright install chromium)
```

Other launch failures (for example missing system libraries) are reported as
`cannot launch chromium: <first line>` followed by the install command and
the `E2E_SKIP_BROWSER=1` escape hatch. On a machine where the system
libraries are missing, `python -m playwright install --with-deps chromium`
installs them too (it needs root).

## Usage

```python
from e2e_support.browser import BrowserSession
from e2e_support.server import LiveServer

with LiveServer(app) as server, BrowserSession() as session:
    scenario = session.new_scenario("home page", base_url=server.url)
    scenario.page.goto("/")
    scenario.close()
```

Playwright's sync API allows one driver per thread and cannot run inside a
running asyncio loop. Behave scenarios and pytest tests are synchronous, so
this only matters for code that starts a session from async code: do it in
a separate thread.

## How it is tested

Pytest (`libs/e2e-support/tests/test_browser.py`, tagged `browser`; they are
skipped when `E2E_SKIP_BROWSER` is set or no browser is installed): relative
navigation against a live server, cookie isolation between two scenarios,
the timeout taken from the settings, context options, the context-manager
protocol and idempotent stop, and, with a stub driver, the message raised
when the browser cannot launch.
