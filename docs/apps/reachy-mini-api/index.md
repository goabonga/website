# Reachy Mini API

Internal FastAPI service used by the Reachy Mini robot to fetch reports,
notifications and server status, and to exchange real-time messages over a
WebSocket. It is a member of the uv workspace under `apps/reachy-mini-api`
(distribution `reachy-mini-api`, import package `reachy_mini_api`).

The service is stateless: no database, no Celery worker and no beat
scheduler.

The application is built as a sequence of features. Each page below
documents one feature as it exists in the code.

1. [Application foundation](01-foundation.md) - settings, FastAPI
   application, CORS and health endpoint.
2. [Dual-stream logging](02-logging.md) - informational logs on stdout,
   problems on stderr, request logging with context.
3. [JWT authentication](03-jwt-auth.md) - bearer token validation against
   the issuer JWKS and scope checks.
4. [Reports and notifications](04-reports.md) - daily report, quick update
   and notification endpoints.
5. [Server and services status](05-status.md) - host information and the
   list of monitored services.
6. [WebSocket channel](06-websocket.md) - real-time messages on `/ws`.
