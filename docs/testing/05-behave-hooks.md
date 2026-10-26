# Behave hooks

`e2e_support.behave_hooks` plugs the browser session into behave. An
application keeps its own in-process scenarios and gains `@browser`
scenarios by calling the hooks from its `features/environment.py`.

## What it does

For a scenario tagged `@browser` (or in a feature carrying the tag) the hooks
provide:

| Attribute | Content |
| --- | --- |
| `context.page` | The Playwright `Page` of the scenario |
| `context.browser_context` | Its isolated `BrowserContext` |
| `context.base_url` | The address of the application under test |
| `context.e2e.scenario` | The `BrowserScenario` (diagnostics, `assert_no_browser_errors`) |

Scenarios without the tag are left alone, and nothing is started (no
browser, no server) when no `@browser` scenario runs.

## Wiring an application

```python
# apps/<app>/features/environment.py
from e2e_support import behave_hooks as e2e
from <module>.main import app


def before_all(context):
    e2e.before_all(context)
    # ... the application's own setup


def before_scenario(context, scenario):
    # ... the application's own in-process setup (database, mocks)
    e2e.before_scenario(
        context, scenario, base_url=lambda: e2e.live_server(context, "app", app).url
    )


def after_scenario(context, scenario):
    e2e.after_scenario(context, scenario)
    # ... the application's own cleanup


def after_all(context):
    e2e.after_all(context)
```

| Hook | Role |
| --- | --- |
| `before_all(context)` | Reads the [settings](02-settings.md) into `context.e2e`; with `E2E_SCREENSHOTS=steps` it also registers `after_step` |
| `before_tag(context, tag)` | Optional: skips a `@browser` scenario as soon as its tag is seen |
| `before_scenario(context, scenario, base_url=None, **context_options)` | Starts the browser on first use, opens the scenario context, sets `page`, `browser_context`, `base_url` |
| `after_scenario(context, scenario)` | Closes the context; if the scenario failed, saves the [artifacts](04-diagnostics.md) and prints their directory |
| `after_step(context, step)` | With `E2E_SCREENSHOTS=steps`, keeps a screenshot after every step of a `@browser` scenario (registered by `before_all`, nothing to wire) |
| `after_all(context)` | Stops the browser and every server started by `live_server` |

`base_url` is a string or, better, a callable: it is only called for
scenarios that really run, so the application is served only when needed.
`context_options` (`locale`, `viewport`, ...) go to Playwright's
`new_context`.

`live_server(context, name, app, **options)` serves `app` once per run
(see [Live server](01-live-server.md)) and returns the same server on later
calls; `after_all` stops it. Use one name per served application.

Behave drops attributes assigned on `context` when a scenario ends, so the
run-wide state lives in the `context.e2e` object (`E2EState`) and is
mutated, not reassigned.

## Skipping

A `@browser` scenario is skipped, not failed, when:

- `E2E_SKIP_BROWSER` is true: `browser scenarios are disabled
  (E2E_SKIP_BROWSER)`;
- the browser cannot be launched, typically because it is not installed: `the
  chromium browser is not installed (install it with: python -m playwright
  install chromium)`.

The reason is written once per run to the real standard error (behave hides
the output of passing hooks), and the browser launch is attempted only once:
an uninstalled browser costs one failed launch, not one per scenario. The
usual way to run only the in-process scenarios is still the tag filter:
`behave -t ~@browser`.

## How it is tested

Pytest (`libs/e2e-support/tests/test_behave_hooks.py`) runs behave in a
subprocess on a small project (`tests/behave_project`) wired exactly like
the example above, against a toy site:

- browser scenarios get a page, a context and a base URL; scenarios without
  the tag get none; a feature-level tag works; contexts do not share
  cookies;
- a failing browser scenario leaves its screenshot, trace and console log;
- with `E2E_SCREENSHOTS=steps` every step of a passing scenario leaves a
  numbered screenshot in `steps/`, and none is kept by default;
- with `E2E_SKIP_BROWSER=1` the browser scenarios are skipped and no
  artifacts are written;
- with an empty `PLAYWRIGHT_BROWSERS_PATH` they are skipped with the install
  command, reported once.
