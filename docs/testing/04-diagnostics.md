# Diagnostics and failure artifacts

A browser scenario that fails is hard to debug from a stack trace alone.
Every `BrowserScenario` therefore records what the browser reported and, when
the scenario fails, keeps enough evidence to replay it.

## What it records

`BrowserScenario.diagnostics` (an `e2e_support.diagnostics.Diagnostics`)
listens to the whole browser context, so popups and new tabs are covered:

- every console message (`log`, `warning`, `error`, ...), with its source
  location;
- every uncaught page error (an exception thrown in the page).

`diagnostics.errors` returns the console errors and the page errors.

## Asserting that the page is healthy

```python
scenario.assert_no_browser_errors()
scenario.assert_no_browser_errors(ignore=[r"favicon\.ico"])
```

The assertion raises `AssertionError` listing every error, for example:

```text
the browser reported 1 error(s):
  - [console:error] boom from console (http://127.0.0.1:39431/console:0)
```

`ignore` holds regular expressions matched with `re.search` against the
error text. Browsers log a console error for a missing `favicon.ico`; ignore
it explicitly when the application does not serve one.

## Artifacts of a failed scenario

`BrowserScenario.finish(failed=True)` writes, in
`<E2E_ARTIFACTS_DIR>/<scenario name>/`:

| File | Content |
| --- | --- |
| `screenshot.png` | Full-page screenshot of the page (`screenshot-2.png`, ... for other open pages) |
| `page.html` | The HTML of the page, preceded by a comment with its URL (`page-2.html`, ...) |
| `console.log` | The recorded console messages and page errors |
| `trace.zip` | Playwright trace (DOM snapshots, screenshots, network), unless `E2E_TRACE` is off |

Open a trace with `python -m playwright show-trace <dir>/trace.zip`.

The directory name is the scenario name made file-system safe; two
scenarios with the same name (outline rows) get `-2`, `-3`, ... suffixes. A
scenario that passed writes nothing, and capturing never raises: a page that
crashed or closed is skipped so that the artifacts do not hide the failure.
The default directory `artifacts/` is ignored by git.

With `E2E_SCREENSHOTS=scenario` (or `steps`), a scenario that passed also
keeps a `screenshot.png` (and `screenshot-2.png`... for further pages) in
its directory, taken before the context is closed. Nothing else is saved for
a passed scenario.

`BrowserScenario.capture_step(text)` saves the page as it is right now in
`steps/NN-<text>.png`. The number is that of the step, so the files sort in
the order the scenario ran. Nothing is kept (`None` is returned) while the
page is still blank because no navigation happened yet, when the page looks
exactly like the previous capture, or when it crashed or closed: a
screenshot never fails a scenario, and a gap in the numbering means that
the step showed nothing new. The behave hooks call it after every step when
`E2E_SCREENSHOTS=steps`.

`finish(failed)` returns the list of saved files and always closes the
context. `close()` is `finish(failed=False)`.

## How it is tested

Pytest (`libs/e2e-support/tests/test_diagnostics.py`, tagged `browser`):
console and page-error capture against a real page, the error assertion and
its `ignore` patterns, nothing saved for a passed scenario, the four files of
a failed one (PNG signature, HTML content, console log, valid trace archive),
several open pages, the trace switched off, name collisions, `slugify` and
the rendering of entries.
