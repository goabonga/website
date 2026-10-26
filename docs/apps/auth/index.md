# Auth

Centralized OIDC/OAuth2 authentication service of the platform: user
accounts, sessions, multi-factor authentication, an OAuth2/OpenID Connect
authorization server and multi-tenant organisations.

The application is the workspace member `apps/auth` (distribution `auth`,
import package `auth`, ASGI entry point `auth.main:app`). It is a FastAPI
service backed by PostgreSQL (SQLAlchemy 2.0 async, Alembic migrations) with
a Celery worker for background work.

## Features

The application is documented feature by feature, in the order in which each feature builds on the previous ones.

1. [Application foundation](01-foundation.md): Package, settings, logging, health check and Swagger UI.
2. [Data model and migrations](02-data-model.md): SQLAlchemy models and the Alembic migration chain.
3. [Signing keys](03-signing-keys.md): Encrypted RSA signing keys and the public JWKS endpoint.
4. [Multi-tenancy and OIDC discovery](04-tenancy.md): Tenant resolution, issuer, branding, trust policies, outbound webhooks and discovery.

## Testing

Each feature has pytest tests and a behave scenario file. Most scenarios run
in process: the database session, Redis, SMTP and the outbound HTTP calls are
replaced by mocks and fakes, so no infrastructure is needed.

The features that have HTML pages also have **browser scenarios**
(`features/browser/<feature>.feature`, every scenario tagged `@browser`). They
drive the pages in a real Chromium through Playwright, with the application
served on a real local socket by the `libs/e2e-support` library (see
[browser tests](../../testing/index.md)). The server runs in a thread of the
behave process, so the SQLite stand-in of the database, the captured e-mails
and the patched settings are the ones of the in-process scenarios. Federation
is played against the fake OpenID provider of the library, the client
applications and the webhook receiver by small servers started by the steps.
Each feature page lists its browser scenarios under *Tests*.

```bash
uv run --package auth --group dev pytest apps/auth
uv run --package auth --group dev behave apps/auth/features                 # everything
uv run --package auth --group dev behave apps/auth/features -t @browser     # browser scenarios
uv run --package auth --group dev behave apps/auth/features -t ~@browser    # in-process scenarios
```

The browser is installed once with `uv run python -m playwright install
chromium`. The scenarios are skipped, not failed, when it is missing or when
`E2E_SKIP_BROWSER=1` is set; `E2E_HEADLESS=false` opens the window to watch a
run and `E2E_SLOWMO=250` slows it down. A failed scenario leaves its
screenshot, trace, page HTML and console log under `artifacts/` (git-ignored).
