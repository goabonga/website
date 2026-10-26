# Browser testing

The applications that render HTML are tested twice: by the in-process
scenarios and tests that every application already has, and by behave
scenarios tagged `@browser` that drive a real browser through
[Playwright](https://playwright.dev/python/).

The shared machinery lives in the `e2e-support` library, a uv workspace
member under `libs/e2e-support` (distribution `e2e-support`, import package
`e2e_support`). It is a development-only support library: it is not an
application, it is not deployed and it is not a release component.

The library is built as a sequence of features. Each page below documents
one feature as it exists in the code.

1. [Live server](01-live-server.md) - serve an ASGI application on a real
   port for the duration of a test.
2. [Settings](02-settings.md) - the `E2E_*` environment variables.
3. [Browser session](03-browser-session.md) - one browser per run, one
   isolated context per scenario.
4. [Diagnostics and failure artifacts](04-diagnostics.md) - console and
   page-error capture, screenshot, trace and HTML of failed scenarios.
