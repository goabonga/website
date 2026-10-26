# frontend

`frontend` is the FastAPI server behind the public website. It is a member of
the uv workspace (`apps/frontend`, import package `frontend`). It has no
database and no background worker.

The application is built feature by feature. Each page below documents one
feature: what it does, its settings, and how it is tested with pytest and
behave.

| Page | Feature |
|------|---------|
| [Foundation](01-foundation.md) | settings, application factory, health check, CORS |
| [Logging](02-logging.md) | stdout/stderr split and request context in log lines |
| [Web client](03-web-client.md) | Vite and TypeScript sources, build and template generator |
| [SPA serving](04-spa-serving.md) | Template rendering, runtime configuration and static files |
| [security.txt](05-security-txt.md) | RFC 9116 vulnerability disclosure contact |
| [Server-side analytics](06-analytics.md) | Page view tracking sent to the analytics service |

## Running the tests

```bash
uv run --package frontend --group dev pytest apps/frontend
uv run --package frontend --group dev behave apps/frontend/features
```

The pytest suite lives in `apps/frontend/tests/`. Each feature also has a
behave scenario file in `apps/frontend/features/`; the scenarios run
in-process against the ASGI application and need no external service.
