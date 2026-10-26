# Deployment

How the `team` application runs in production. The production inventory and its
secrets are kept outside this repository; this page lists the processes, the
settings and the secrets they need, without any value.

## Processes

The application is deployed as three systemd units sharing one Unix user and one
code base.

| Unit | Command | Role |
|------|---------|------|
| `team` | `gunicorn team.main:app`, 2 workers, Uvicorn worker class, Unix socket | The HTTP API behind nginx |
| `team-worker` | `celery -A team.celery:celery_app worker --queues=team --concurrency=2` | Runs the agents ([Agent runner](15-agent-runner.md)), the dispatcher, the webhook events and the maintenance jobs |
| `team-beat` | `celery -A team.celery:celery_app beat` | Enqueues the periodic tasks; exactly one instance may run |

Older deployments referenced the code as `app.main:app` and
`app.celery:celery_app`; from this repository the import package is `team`, so
those paths become `team.main:app` and `team.celery:celery_app`. The Celery task
names changed the same way (`app.tasks...` became `team.tasks...`): drain the
queue before deploying a release that crosses the rename, otherwise the worker
receives messages for tasks it does not know.

The API is internal. nginx publishes it on an internal host name, reachable only
from the VPN subnet, with a certificate issued by the internal certificate
authority, and uses `/health` as the probe endpoint (restricted to loopback).
The units run as the same operating system user, so the worker sees the
workspace the API prepared.

Agents call the other services of the platform (mailler, analytics, auth)
through their Unix sockets (`unix://` base URLs, see
[Service tools](12-service-tools.md)): the user of the units must belong to the
operating system group of each of those services, and nginx's user to the group
of this one.

## Data stores

- **PostgreSQL**: a dedicated `team` database reached through the local socket
  with peer authentication (`DATABASE_URL=postgresql+asyncpg://team@/team?host=/var/run/postgresql`,
  converted to a synchronous URL by Alembic). The `pgvector` extension must be
  installable in it: the revision `0004_create_memory_entries` runs `CREATE
  EXTENSION IF NOT EXISTS vector`, so either the migration user is allowed to
  do it or the extension is enabled beforehand. Run the migrations on every
  release: `alembic -c apps/team/alembic.ini upgrade head` (a database migrated by
  the standalone application is stamped once, see [Seed data](18-seed-data.md)).
  The `postgres_query` tool connects with the same URL, so the database role
  should be limited to what the agents may read.
- **Redis**: one logical database for the Celery broker and another for the
  result backend (`CELERY_BROKER_URL`, `CELERY_RESULT_BACKEND`), and one for the
  token validation caches (`REDIS_URL`).
- **Workspace**: a directory writable by the user of the units
  (`WORKSPACE_DIR`), where each task gets a temporary subdirectory.

## Settings in production

| Feature page | Variables |
|--------------|-----------|
| [Foundation](01-foundation.md) | `LOG_LEVEL`, `APP_NAME`, `DOCS_ENABLED`, `DATABASE_ECHO`, `DATABASE_URL`, `CORS_*` |
| [OAuth2 authentication](02-authentication.md) | `REDIS_URL`, `REDIS_KEY_PREFIX`, `OAUTH2_ISSUER`, `OAUTH2_TRUSTED_ISSUERS`, `OAUTH2_SWAGGER_CLIENT_ID`, `OAUTH2_CLIENT_ID`, `TOKEN_INTROSPECTION_CACHE_TTL`, `OAUTH2_CLIENT_CACHE_TTL`, `JWKS_CACHE_TTL` |
| [Service tools](12-service-tools.md) | `SERVICES_BASE_URL`, `BILLING_BASE_URL`, `MAILLER_BASE_URL`, `ANALYTICS_BASE_URL`, `AUTH_BASE_URL` |
| [Workspace tools](13-workspace-tools.md) | `WORKSPACE_DIR`, `GITHUB_OWNER` |
| [Agent runner](15-agent-runner.md) | `CELERY_BROKER_URL`, `CELERY_RESULT_BACKEND` |

The API unit needs all of them. The worker needs the database, Celery, Redis,
workspace, service URLs and GitHub owner settings; the beat unit only needs the
Celery settings and the database.

### Secrets

Four values are secrets and are never written in the environment file. They are
delivered with systemd credentials, which the application reads from
`$CREDENTIALS_DIRECTORY` before falling back to the environment:

- `OPENAI_API_KEY` (API for the embeddings, worker for the agents)
- `ANTHROPIC_API_KEY` (worker)
- `OAUTH2_CLIENT_SECRET` (API for the token exchange, worker for the service
  tools)
- `GITHUB_TOKEN` (worker; agents can also carry their own token in their
  configuration)

## Dependencies on other applications

- `auth`: OIDC issuer for the JWKS, token introspection and token exchange; the
  issuers are listed in `OAUTH2_ISSUER` and `OAUTH2_TRUSTED_ISSUERS`.
- `billing`, `mailler`, `analytics` and `auth`: called by the agents through the
  service tools, with the OAuth2 client secret as bearer token unless the agent
  has its own token.
- Shared infrastructure: PostgreSQL with `pgvector`, Redis, the OpenAI and
  Anthropic APIs and the GitHub API.

## Ansible

The [python_app](../../ansible/roles/python_app.md) role deploys the three
units from the catalog of the `apps` playbook
([Deploying applications](../../ansible/05-deploying-apps.md)): enable `team`
in `website_apps_enabled` and it brings the components `team`, `team_worker`
and `team_beat`.

- `team` runs gunicorn on the socket `/run/team/team.sock`, with a `/health`
  probe, a `team` database with the `pgvector` extension migrated with Alembic
  on each release, and an nginx virtual host on the internal listen address
  with a certificate from the internal certificate authority.
- `team_worker` consumes the queue `team`. The worker and the beat have
  `/usr/bin` and `/usr/local/bin` in their `PATH`, so that the `git` tools
  find the executable.
- The API and the worker join the groups `mailler`, `analytics` and `auth`
  and get `MAILLER_BASE_URL`, `ANALYTICS_BASE_URL` and `AUTH_BASE_URL` as
  `unix://` URLs of their sockets. Enable those applications first: a missing
  group is reported and the run must be repeated once it exists.
- Secrets ([Secrets](../../ansible/03-secrets.md)): `OPENAI_API_KEY` is
  required; `ANTHROPIC_API_KEY`, `GITHUB_TOKEN` and, on the API,
  `OAUTH2_CLIENT_SECRET` are deployed only when set.
- The catalog sets none of `BILLING_BASE_URL`, `SERVICES_BASE_URL`,
  `GITHUB_OWNER` and `WORKSPACE_DIR`. Add them with `env_vars` in
  `website_apps_overrides` when the agents need them. Without `WORKSPACE_DIR`
  the workspace is under the private `/tmp` of the unit, which systemd
  empties when the unit restarts.

## Verifying a deployment

```bash
systemctl status team team-worker team-beat
curl --unix-socket /run/team/team.sock http://localhost/health
```
