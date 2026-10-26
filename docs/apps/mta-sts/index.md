# mta-sts

Minimal FastAPI service, member of the uv workspace under `apps/mta-sts`
(distribution `mta-sts`, import package `mta_sts`). Its purpose is to serve
the MTA-STS policy (RFC 8461) of a mail domain, so that sending mail servers
know whether TLS must be enforced when delivering mail to the domain.

The service is stateless: no database, no Redis, no Celery worker and no
beat scheduler.

The application is built as a sequence of features. Each page below
documents one feature as it exists in the code.

1. [Application foundation](01-foundation.md) - settings, FastAPI
   application and health endpoint.
2. [Dual-stream logging](02-logging.md) - informational logs on stdout,
   problems on stderr.
