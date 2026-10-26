# webhooks

Minimal FastAPI gateway, member of the uv workspace under `apps/webhooks`
(distribution `webhooks`, import package `webhooks`). It receives webhooks
from external providers and forwards the original payload, as is, to
internal services over a Unix socket or HTTP.

The service is stateless: no database, no Redis, no Celery worker and no
beat scheduler.

The application is built as a sequence of features. Each page below
documents one feature as it exists in the code.

1. [Application foundation](01-foundation.md) - settings, FastAPI
   application and health endpoint.
