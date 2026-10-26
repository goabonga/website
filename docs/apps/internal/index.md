# internal

Internal admin dashboard for managing platform services: a FastAPI application
that renders server-side Jinja2 pages for operators. It authenticates users
against an OAuth2 / OIDC server and talks to the other platform services over
HTTP. The Python package is `internal`, a member of the uv workspace under
`apps/internal`.

The application was assembled feature by feature; each page below documents one
feature, in the order they were introduced.

## Features

1. [Application foundation](01-foundation.md)
2. [OAuth2 authentication](02-authentication.md)
3. [Analytics dashboards](03-analytics.md)
4. [Admin dashboard and chat history](04-dashboard.md)
5. [VPN session management](05-vpn.md)
6. [Billing administration](06-billing.md)
   - [SaaS client bindings](06a-billing-client-bindings.md)
   - [Checkout URL allow-list and branding](06b-billing-checkout-urls.md)
   - [Plan slug and free-form limits](06c-billing-plans.md)
7. [Team AI administration](07-team.md)
8. [Mailler statistics](08-mailler.md)
9. [Contact management](09-contacts.md)
10. [Contact groups](10-contact-groups.md)
11. [Email templates](11-email-templates.md)
12. [Email campaigns](12-email-campaigns.md)
13. [Knowledge namespaces](13-namespaces.md)
14. [System prompts](14-prompts.md)
15. [Knowledge base](15-knowledge.md)

## Running locally

```bash
uv sync --all-groups --package internal
uv run --package internal uvicorn internal.main:app --reload
```

Tests are run from the repository root:

```bash
uv run --package internal pytest apps/internal
uv run --package internal behave apps/internal/features
```

The scenarios of `features/browser/` (tagged `@browser`) run in a real Chromium: the
application is served on a local socket and users sign in through the fake OpenID
provider of `libs/e2e-support`, so the login redirects, the token validation and the
token exchange are the real code talking to a real HTTP server. The database and the
mocked service clients are those of the in-process scenarios (the server runs in a
thread of the same process). The browser must be installed once
(`uv run playwright install chromium`):

```bash
uv run --package internal --group dev behave apps/internal/features -t @browser    # only the browser scenarios
uv run --package internal --group dev behave apps/internal/features -t ~@browser   # only the in-process ones
E2E_SKIP_BROWSER=1 uv run --package internal --group dev behave apps/internal/features   # skip the browser
E2E_HEADLESS=false uv run --package internal --group dev behave apps/internal/features -t @browser   # watch it
```

A failed browser scenario leaves a screenshot, the page, the console log and a trace in
`artifacts/` (see [the browser tests](../../testing/index.md) for the settings and the
steps). Every other page of this documentation lists, in its Tests section, the browser
scenarios of its feature.

`pytest` covers the code with unit and route-handler tests. `behave` runs one
scenario file per feature, in-process unless it is tagged `@browser`: the application is driven through
an ASGI transport, the database is a throw-away SQLite file and every outbound
service client is replaced by a mock. No PostgreSQL, Redis or network access is
needed.

## Deployment

The application is deployed from this repository by the `goabonga.website` Ansible collection, as two processes that share
the same code and the same system user:

| Process | Entry point | Notes |
| --- | --- | --- |
| API | `gunicorn internal.main:app` (Uvicorn worker, one worker) | served over a Unix socket behind nginx; `GET /health` is the probe |
| Celery worker | `celery -A internal.celery:celery_app worker -Q internal` | concurrency 2; processes knowledge generation and validation |

Notes for operators:

- The service user must belong to the groups of the services it reaches over Unix sockets (mailler, billing and team), because
  `MAILLER_SOCKET_PATH`, `BILLING_SOCKET_PATH` and `TEAM_SOCKET_PATH` point at their runtime sockets.
- The database is the platform's shared PostgreSQL database (peer authentication over the Unix socket, with the pgvector
  extension); the worker needs `DATABASE_URL` too. Redis serves the introspection and token-exchange caches and, unless overridden,
  the Celery broker and result backend.
- Secrets (`SECRET_KEY`, `OAUTH2_CLIENT_SECRET`, `OPENAI_API_KEY`) are delivered as systemd credentials and read through
  `internal.config.get_credential`; everything else is plain environment configuration. Set `COOKIE_SECURE=true` behind HTTPS.
- The dashboard must only be reachable from the operators' private network: access control belongs in nginx, the application
  only checks scopes.
- The existing inventory entries (`internal` and `internal_worker`) still reference the previous layout of the source
  repository (`app.main:app`, `app.celery:celery_app`); they must point at the import paths above when they are switched to
  this package. There is no beat process for this application.
