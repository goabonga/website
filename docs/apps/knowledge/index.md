# knowledge

Vector storage and semantic search service for AI agents, LLMs and RAG
applications. It is the `knowledge` member of the uv workspace
(`apps/knowledge`, import package `knowledge`).

The service is built as a sequence of features. Each page below documents
one feature: what it does, its endpoints, its settings, its data model and
how it is tested with pytest and behave.

## Features

1. [Foundation](00-foundation.md): application factory, internal
   sub-application, settings, logging and the health check.
2. [Data model](01-data-model.md): SQLAlchemy models, async session and the
   Alembic migration chain.
3. [OAuth2 authentication](02-authentication.md): bearer token validation,
   token exchange, scopes and tenant resolution.
4. [Collections](03-collections.md): collection API, ownership and access
   levels.
5. [Documents](04-documents.md): document API and OpenAI embeddings.
6. [Semantic search](05-search.md): vector similarity search over
   collections.
7. [Collaborators and invitations](06-collaboration.md): sharing collections
   with other users.
8. [Usage quotas](07-quotas.md): plan limits and per-tenant API call
   tracking.
9. [Multi-tenant resolution](08-multi-tenancy.md): tenants from path,
   subdomain or custom domain.
10. [Billing integration](09-billing.md): plans, subscriptions and the
    subscription webhook.
11. [Plan limits from billing](09a-plan-limits.md): quota limits read from the
    billing plans, with a configured fail-safe.
12. [Email delivery](10-email.md): MJML templates sent through the
    mailler service.
13. [MCP releases](11-releases.md): GitHub release webhook and public
    download API.
14. [Background tasks](12-background-tasks.md): Celery worker, email tasks and
    scheduled workspace deletion.
15. [Custom domains](13-custom-domains.md): domains of Enterprise organizations
    registered in the custom-domain service, status webhooks and reconciliation.
16. [Web authentication](14-web-authentication.md): browser signin, signup and
    account pages.
16. [Landing and dashboard](15-web-dashboard.md): public pages, dashboard and
    MCP download page.
17. [Collection and document pages](16-web-collections-documents.md):
    managing the knowledge base from the browser.
18. [Search page](17-web-search.md): searching the workspace from the browser.
19. [Workspace settings and plans](18-workspace-settings.md): switching,
    upgrading and renaming workspaces.
20. [Workspace members](19-workspace-members.md): invitations, roles and
    removals.
21. [Workspace deletion](20-workspace-deletion.md): email-confirmed and
    scheduled deletion.
22. [Workspace custom domain](21-workspace-domain.md): managing the custom
    domain from the browser.
23. [Deployment](22-deployment.md): processes, database, Redis, configuration
    and sockets.

## Running the tests

Every command runs from the root of the workspace:

```bash
uv run --package knowledge --group dev pytest apps/knowledge
uv run --package knowledge --group dev behave apps/knowledge/features
```

The pytest suite and the in-process behave scenarios use mocks and fakes and never
need a database, Redis or any external service.

The behave scenarios tagged `@browser` drive the web pages in a real Chromium through
Playwright, with the fake OpenID provider of `e2e-support` for the sign-in. They serve
the application on a local port, with a SQLite file instead of PostgreSQL and fakes for
the platform services. They are part of the command above and can be selected or left out
on their own:

```bash
uv run --package knowledge --group dev behave apps/knowledge/features -t @browser
uv run --package knowledge --group dev behave apps/knowledge/features -t ~@browser
```

A `@browser` scenario is skipped, not failed, when `E2E_SKIP_BROWSER=1` is set or when
the browser is not installed (`python -m playwright install chromium`). `E2E_HEADLESS=false`
shows the browser, and a failed scenario leaves a screenshot, a trace and the page in
`artifacts/`; see [Browser testing](../../testing/index.md) for the other settings.
