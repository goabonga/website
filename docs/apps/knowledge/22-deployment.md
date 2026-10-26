# Deployment

The service runs as three processes that share one code base, one PostgreSQL
database and one Redis. They are deployed from this repository to a Debian host
by the Ansible tooling of the platform (the `ansible/` directory holds the
`goabonga.website` collection); nothing is published to PyPI and no Debian
package is built. This page lists what a deployment definition has to provide;
it contains no secret value and no real host name.

## Processes

| Component | Command | Notes |
| --- | --- | --- |
| API | `gunicorn knowledge.main:app` (2 workers) | Listens on a Unix socket (`/run/knowledge/knowledge.sock`) behind nginx. `GET /health` is the health check. |
| Worker | `celery -A knowledge.celery:celery_app worker -Q "$CELERY_QUEUE" --concurrency 2` | Consumes the queue of `CELERY_QUEUE` (`knowledge` by default). It needs no `sudo`, nginx or certbot: the emails go through mailler and the custom domains through the custom-domain service. |
| Beat | `celery -A knowledge.celery:celery_app beat` | Emits the deletion tasks (`DELETION_CHECK_INTERVAL`) and the custom domain reconciliation (`CUSTOM_DOMAIN_RECONCILE_INTERVAL`). |

All three run as the same system user and read the same environment file. The
module paths changed with the move to this repository (`app.main:app` and
`app.celery:celery_app` became `knowledge.main:app` and
`knowledge.celery:celery_app`), as did the task names (see [Background
tasks](12-background-tasks.md)).

## Database

PostgreSQL with the `pgvector` extension available (the first migration runs
`CREATE EXTENSION IF NOT EXISTS vector`). The application uses the async
driver (`postgresql+asyncpg://...`), through a Unix socket in production
(`postgresql+asyncpg://knowledge@/knowledge?host=/var/run/postgresql`).
Migrations run on every deployment, from the root of the checkout:

```bash
uv run --package knowledge alembic -c apps/knowledge/alembic.ini upgrade head
```

The command is idempotent: it does nothing when the schema is current (see
[Data model](01-data-model.md)).

## Redis

One Redis serves the Celery broker and result backend (`CELERY_BROKER_URL`,
`CELERY_RESULT_BACKEND`) and the application cache (`REDIS_URL`: token exchange
and billing plans), usually on a dedicated database index.

## Configuration

Settings are environment variables, written to a file readable only by the
service user. Each feature page lists its variables; by component:

| Component | Variables |
| --- | --- |
| API | `LOG_LEVEL`, `APP_NAME`, `DOCS_ENABLED`, `DATABASE_URL`, `REDIS_URL`, `CELERY_BROKER_URL`, `CELERY_RESULT_BACKEND`, `EMBEDDING_MODEL`, `EMBEDDING_DIMENSION`, search and rate limit settings, `OAUTH2_ISSUER`, `OAUTH2_SWAGGER_CLIENT_ID`, `OAUTH2_FRONTEND_CLIENT_ID`, `OAUTH2_CLIENT_ID`, `OAUTH2_TOKEN_CACHE_TTL`, `APP_BASE_URL`, `COOKIE_SECURE`, `COOKIE_DOMAIN`, the operator settings (`OPERATOR_NAME`, `CONTACT_EMAIL`, `SALES_EMAIL`, `LEGAL_EMAIL`, `PRIVACY_EMAIL`, `SUPPORT_URL`), `QUOTA_FALLBACK_LIMITS`, `TENANT_BASE_DOMAIN`, `TENANT_CUSTOM_DOMAIN_LOOKUP`, and the platform services: `BILLING_API_URL` or `BILLING_SOCKET_PATH`, `BILLING_APP_SLUG`, `BILLING_SAAS_ID`, `BILLING_CLIENT_ID`, `BILLING_CHECKOUT_SUCCESS_URL`, `BILLING_CHECKOUT_CANCEL_URL`, `BILLING_CACHE_TTL`, `BILLING_FAILURE_BACKOFF`, `CUSTOM_DOMAIN_SERVICE_URL` or `CUSTOM_DOMAIN_SERVICE_SOCKET_PATH`, `CUSTOM_DOMAIN_CLIENT_ID`, `CUSTOM_DOMAIN_CNAME_TARGET`, `CUSTOM_DOMAIN_WEBHOOK_TOLERANCE`. |
| Worker | `DATABASE_URL`, `REDIS_URL`, `CELERY_*`, `APP_BASE_URL`, `OAUTH2_ISSUER`, `OAUTH2_CLIENT_ID`, `MAILLER_URL` or `MAILLER_SOCKET_PATH`, `MAILLER_CLIENT_ID`, `MAILLER_MAX_RETRIES`, `MAILLER_RETRY_DELAY`, `CUSTOM_DOMAIN_SERVICE_URL` or `CUSTOM_DOMAIN_SERVICE_SOCKET_PATH`, `CUSTOM_DOMAIN_CLIENT_ID`, `CUSTOM_DOMAIN_RECONCILE_INTERVAL`, `SERVICE_TIMEOUT`. |
| Beat | `DATABASE_URL`, `CELERY_*`, `DELETION_CHECK_INTERVAL`, `CUSTOM_DOMAIN_RECONCILE_INTERVAL`. |

`SUPPORT_URL` is read by the API only: it is passed to the workspace deletion
email task as an argument, so the worker does not need it.

Secrets are not written to the environment file. They are provided as systemd
encrypted credentials and read through `get_credential` (see
[Foundation](00-foundation.md)):

| Secret | Used by |
| --- | --- |
| `OPENAI_API_KEY` | API and worker (embeddings). |
| `OAUTH2_CLIENT_SECRET` | API (token validation, exchange and web sign-in); also the default client secret of the platform services. |
| `MAILLER_CLIENT_SECRET`, `CUSTOM_DOMAIN_CLIENT_SECRET`, `BILLING_CLIENT_SECRET` | Worker and API (client credentials of each service; each falls back to `OAUTH2_CLIENT_SECRET` when empty). |
| `BILLING_WEBHOOK_SECRET`, `CUSTOM_DOMAIN_WEBHOOK_SECRET`, `GITHUB_WEBHOOK_SECRET` | API (webhook signatures). Without a value the corresponding webhook refuses every request, so they must be provided in production. |

There is no SMTP secret: the service sends nothing itself.

## Networking and sockets

- nginx proxies the public host to the API socket. Tenant subdomains need a
  wildcard certificate for the base domain (`TENANT_BASE_DOMAIN`); custom domains
  get their own virtual host and certificate at runtime.
- The service user must be able to reach the sockets of the billing service
  (`BILLING_SOCKET_PATH`), of the mailler service (`MAILLER_SOCKET_PATH`) and of the
  custom-domain service (`CUSTOM_DOMAIN_SERVICE_SOCKET_PATH`) when sockets are used, which is
  done by adding it to their groups; otherwise their HTTP URLs are used.
- The services call back the API: billing posts to `/webhooks/billing` and the custom-domain
  service to `/webhooks/custom-domain` on the internal sub-application. These URLs are
  registered on the SaaS application in billing and on the authorized client in the
  custom-domain service, and must be reachable from them.
- Nothing about nginx virtual hosts, certificates or `sudo` belongs to this application any more:
  the custom-domain service writes the virtual host that proxies a customer domain to the API
  socket (the upstream is part of the registration of the client in that service, and the nginx
  user needs access to the socket).
- After the first deployment of the platform services, the templates are imported into mailler
  and the OAuth2 client is registered in all three services, see [Platform onboarding](23-platform-onboarding.md).
- Logs go to stdout (info) and stderr (warning and above), captured by systemd
  into separate files (see [Foundation](00-foundation.md)).

## Local development

`apps/knowledge/compose.yml` starts PostgreSQL with pgvector and Redis with the
default ports of the settings, which is enough to run the API, the migrations
and the worker on a workstation (see the README of the application).
