# Deployment

How the `billing` service runs in production. The production inventory and
its secrets are kept outside this repository; this page lists the processes,
the settings and the secrets they need, without any value.

## Processes

The service is deployed as three systemd units sharing one Unix user and one
code base.

| Unit | Command | Role |
|------|---------|------|
| `billing` | `gunicorn billing.main:app`, 2 workers, Uvicorn worker class, Unix socket | The HTTP API behind nginx |
| `billing-worker` | `celery -A billing.celery:celery_app worker --queues=billing --concurrency=2` | Runs the usage and Stripe sync tasks and delivers the notifications to the tenants; `--queues` must be the value of `CELERY_QUEUE` |
| `billing-beat` | `celery -A billing.celery:celery_app beat` | Enqueues the periodic tasks; exactly one instance may run |

Older deployments referenced the code as `app.main:app` and
`app.celery:celery_app`; from this repository the import package is
`billing`, so those paths become `billing.main:app` and
`billing.celery:celery_app`. The Celery task names changed the same way
(`app.tasks...` became `billing.tasks...`): drain the queue before deploying
a release that crosses the rename.

The API is internal. nginx publishes it on an internal host name, reachable
only from the VPN subnet (listen address and allowed hosts restricted to the
VPN), with a certificate issued by the internal certificate authority, and
uses `/health` as the probe endpoint. Other applications reach the API
through its Unix socket (`/run/billing/billing.sock`); they join the `billing`
operating system group to be allowed to use it, and nginx's user is a member
of the same group.

## Data stores

- **PostgreSQL**: a dedicated `billing` database reached through the local
  socket with peer authentication (`DATABASE_URL=postgresql+asyncpg:///billing`
  for the application, converted to a synchronous URL by Alembic). Run the
  migrations on every release:
  `alembic -c apps/billing/alembic.ini upgrade head`.
- **Redis**: a dedicated logical database for the token validation caches
  (`REDIS_URL`), distinct from the Celery broker and result backend
  databases, which come from shared settings.

## Settings in production

| Feature page | Variables |
|--------------|-----------|
| Foundation | `LOG_LEVEL`, `APP_NAME`, `DOCS_ENABLED`, `DATABASE_ECHO`, `DATABASE_URL` |
| Authentication | `REDIS_URL`, `OAUTH2_ISSUER`, `OAUTH2_TRUSTED_ISSUERS`, `OAUTH2_SWAGGER_CLIENT_ID`, `OAUTH2_CLIENT_ID`, `TOKEN_INTROSPECTION_CACHE_TTL`, `OAUTH2_CLIENT_CACHE_TTL` |
| Stripe service | `STRIPE_PUBLISHABLE_KEY`, `DEFAULT_RECURRING_INTERVAL` |
| Data model | `DEFAULT_CURRENCY` |
| SaaS applications, customers, subscriptions, checkout, usage | `REDIRECT_ALLOWLIST_REQUIRED`, `LIST_DEFAULT_LIMIT`, `LIST_MAX_LIMIT`, `MAX_TRIAL_PERIOD_DAYS`, `CHECKOUT_MAX_QUANTITY`, `USAGE_BATCH_MAX_EVENTS` |
| Client partitioning | `PARTITION_ADMIN_SCOPE`, `PARTITION_ALLOW_UNBOUND`, `PLANS_PUBLIC` |
| Webhooks | `STRIPE_WEBHOOK_REQUIRED_SCOPE`, `SAAS_WEBHOOK_TIMEOUT` |
| Background tasks | `CELERY_BROKER_URL`, `CELERY_RESULT_BACKEND`, `CELERY_QUEUE`, `CELERY_TIMEZONE`, `CELERY_TASK_TIME_LIMIT`, `USAGE_REPORT_INTERVAL`, `USAGE_REPORT_BATCH_SIZE`, `USAGE_CLEANUP_INTERVAL`, `USAGE_RETENTION_DAYS`, `STRIPE_SYNC_INTERVAL` |
| Notification delivery | `SAAS_WEBHOOK_MAX_ATTEMPTS`, `SAAS_WEBHOOK_BACKOFF_SECONDS`, `SAAS_WEBHOOK_BACKOFF_FACTOR`, `SAAS_WEBHOOK_BACKOFF_MAX_SECONDS` |

Every variable except the connection settings has a default, listed on the
page of its feature, and none of them is specific to a tenant. The API unit
needs all of them. The worker and beat units need the database, Celery,
delivery and (for the worker) Stripe settings, and the beat unit the
schedule settings.

The `CELERY_*` and schedule settings must be identical in the three units:
the worker consumes the queue the API publishes to, and the beat unit builds
the schedule from the same variables.

### Secrets

Three values are secrets and are never written in the environment file. They
are delivered with systemd credentials, which the application reads from
`$CREDENTIALS_DIRECTORY` before falling back to the environment:

- `STRIPE_SECRET_KEY` (API and worker)
- `STRIPE_WEBHOOK_SECRET` (API)
- `OAUTH2_CLIENT_SECRET` (API)

## Dependencies on other applications

- `auth`: OIDC issuer for the JWKS, token introspection and token exchange;
  the issuers are listed in `OAUTH2_ISSUER` and `OAUTH2_TRUSTED_ISSUERS`.
- `webhooks`: receives the Stripe events and forwards them, with the
  `Stripe-Signature` header, to `/webhooks/stripe` over the Unix socket.
  The signature is the authentication of that endpoint: no token is needed,
  and one sent by the gateway is ignored unless
  `STRIPE_WEBHOOK_REQUIRED_SCOPE` is set.
- `internal` and the SaaS applications (for instance `knowledge`): clients
  of the API through the socket. Each one uses its own OAuth client, which
  must be bound to its SaaS application (see the client partitioning page);
  the plans are not seeded, they are created through the API.
- Shared infrastructure: PostgreSQL, Redis and the Stripe API.

## First deployment of a tenant

Migrations create no tenant and no plan. After `alembic upgrade head`, an
operator with access to the database creates the first SaaS application and
binds the OAuth client that will administer it, then everything else goes
through the API:

```bash
billing-admin saas create --name "<name>" --slug <slug> --checkout-url <origin>
billing-admin client bind --saas <slug> --client-id <oauth client id>
```

The command reads the same `DATABASE_URL` as the API. The onboarding steps
that follow are described in the client partitioning page.

## Ansible

The [python_app](../../ansible/roles/python_app.md) role deploys the three
units from the catalog of the `apps` playbook
([Deploying applications](../../ansible/05-deploying-apps.md)): enable
`billing` in `website_apps_enabled` and it brings the components `billing`,
`billing_worker` and `billing_beat`.

- `billing` runs gunicorn on the socket `/run/billing/billing.sock`, with a
  `/health` probe, a database `billing` migrated with Alembic on each
  release, and an nginx virtual host on the internal listen address with a
  certificate from the internal certificate authority.
- `billing_worker` consumes the queue `website_billing_celery_queue`
  (`billing` by default) and `billing_beat` publishes the periodic tasks.
- The secrets to provide in `website_secrets` are `STRIPE_SECRET_KEY`,
  `STRIPE_WEBHOOK_SECRET` and `OAUTH2_CLIENT_SECRET` for the API, and
  `STRIPE_SECRET_KEY` for the worker ([Secrets](../../ansible/03-secrets.md)).
- The settings of the table above are the `website_billing_*` variables
  ([Billing](../../ansible/roles/python_app.md#billing)); the settings that
  the three units must share go in `website_billing_shared_env`.
- The SaaS applications and the client bindings can be declared in
  `website_billing_saas_apps` and `website_billing_client_bindings`, which run
  `billing-admin` after the migrations
  ([Onboarding a SaaS application](../../ansible/07-saas-onboarding.md)).

## Verifying a deployment

```bash
systemctl status billing billing-worker billing-beat
curl --unix-socket /run/billing/billing.sock http://localhost/health
```
