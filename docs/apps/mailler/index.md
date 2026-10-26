# mailler

Internal email sending service. Other platform services submit emails to its
HTTP API; mailler queues them in Celery and delivers them through one of
several providers. The application is built as a sequence of features, each
documented on its own page.

- Workspace member: `apps/mailler` (distribution `mailler`, import package `mailler`).
- ASGI entry point: `mailler.main:app` (FastAPI).
- Python 3.11 or newer.

## Features

| Page | Feature |
| --- | --- |
| [Application foundation](01-foundation.md) | Settings, logging, database sessions, health check |
| [OAuth2 authentication](02-authentication.md) | Bearer token validation and scope checks |
| [Email providers](03-providers.md) | Brevo, SendGrid, AWS SES and Protonmail adapters, signatures |
| [Sending emails](04-send.md) | `POST /send`, Celery worker, first migration |
| [Listing and reading emails](05-emails.md) | Paginated list and detail of stored emails |
| [Sending statistics](06-stats.md) | Totals, per-provider and per-day counters |

## Running the tests

From the repository root:

```bash
uv run --package mailler --group dev pytest apps/mailler
uv run --package mailler --group dev behave apps/mailler/features
```

Every feature page lists the pytest modules and the behave feature file that
cover it. Behave scenarios run in-process and need no external service.
