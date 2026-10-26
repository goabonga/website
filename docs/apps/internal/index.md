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
