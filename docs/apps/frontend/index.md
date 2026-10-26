# frontend

`frontend` is the FastAPI server behind the public website. It is a member of
the uv workspace (`apps/frontend`, import package `frontend`). It has no
database and no background worker.

The server renders one page for every path, injecting its runtime
configuration from environment variables, serves the build of the web client
under `/static`, publishes `security.txt`, reports page views to the analytics
service and exposes a health check.

The application is built feature by feature. Each page below documents one
feature: what it does, its settings, and how it is tested with pytest and
behave. The last page covers the deployment.

| Page | Feature |
|------|---------|
| [Foundation](01-foundation.md) | settings, application factory, health check, CORS |
| [Logging](02-logging.md) | stdout/stderr split and request context in log lines |
| [Web client](03-web-client.md) | Vite and TypeScript sources, build and template generator |
| [SPA serving](04-spa-serving.md) | Template rendering, runtime configuration and static files |
| [security.txt](05-security-txt.md) | RFC 9116 vulnerability disclosure contact |
| [Server-side analytics](06-analytics.md) | Page view tracking sent to the analytics service |
| [Deployment](07-deployment.md) | Process, environment, client build and nginx requirements |

## Routes

| Path | Provided by |
|------|-------------|
| `/health` | [Foundation](01-foundation.md) |
| `/.well-known/security.txt` | [security.txt](05-security-txt.md) |
| `/static/*` | [SPA serving](04-spa-serving.md) |
| every other path | [SPA serving](04-spa-serving.md) |

## Running the tests

```bash
uv run --package frontend --group dev pytest apps/frontend
uv run --package frontend --group dev behave apps/frontend/features
```

The pytest suite lives in `apps/frontend/tests/`. Each feature also has a
behave scenario file in `apps/frontend/features/`; the scenarios run
in-process against the ASGI application and need no external service.

The features with pages also have browser scenarios in
`apps/frontend/features/browser/`, tagged `@browser`. They open the
application in Chromium, served on a real socket, with the web client built
from its sources (this needs `node`, `npm` and the npm registry; without them
the scenarios that need the build are skipped with the reason). See [Browser
testing](../testing/index.md). They run with the other scenarios, or alone:

```bash
uv run --package frontend --group dev behave apps/frontend/features -t @browser
```

`E2E_SKIP_BROWSER=1` skips them, and `E2E_HEADLESS=false` shows the browser.
The browser itself is installed once with `uv run playwright install chromium`.
