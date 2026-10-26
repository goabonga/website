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
2. [Dual-stream logging](02-logging.md) - informational logs on stdout,
   problems on stderr, and the application lifespan.
3. [OAuth2 client credentials](03-oauth2.md) - bearer tokens for calls to
   internal services.
4. [Brevo webhook proxy](04-brevo.md) - raw proxy for Brevo events with
   optional HMAC verification.
