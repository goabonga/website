# Deployment

How the `backend` service runs in production. The production inventory and
its secrets are kept outside this repository; this page lists the processes,
the settings and the secrets they need, without any value.

## Processes

The service is deployed as three systemd units sharing one Unix user and one
code base.

| Unit | Command | Role |
|------|---------|------|
| `backend` | `gunicorn backend.main:app`, 2 workers, `uvicorn.workers.UvicornWorker`, Unix socket | The HTTP API behind nginx |
| `backend-worker` | `celery -A backend.celery:celery_app worker --queues=backend --concurrency=4` | Runs Celery tasks (the conversation sync) |
| `backend-beat` | `celery -A backend.celery:celery_app beat` | Enqueues the periodic `sync_dirty_conversations` task; exactly one instance may run |

Gunicorn is a dependency of the package, started from the application
environment. Older deployments referenced the code as `app.main:app` and
`app.celery:celery_app`; from this repository the import package is
`backend`, so those paths become `backend.main:app` and
`backend.celery:celery_app`.

nginx terminates TLS for the public API domain and proxies to the gunicorn
socket; `/health` is the probe endpoint. Because the application
trusts `X-Forwarded-For` and `X-Real-IP` (see the rate limiting page), nginx
must set both headers and the socket must not be reachable another way.

## Data stores

- **PostgreSQL** with the `vector` extension, reached through the local
  socket with peer authentication (`DATABASE_URL=postgresql:///<database>`).
  Run the migrations on every release:
  `alembic -c apps/backend/alembic.ini upgrade head`.
- **Redis**, several logical databases: Celery broker and results, rate
  limiter, sessions and conversation cache, prompt cache. The API and the
  worker must point `SESSION_REDIS_URL` to the same database, otherwise the
  worker cannot see the dirty conversations written by the API.

## Settings in production

The environment file of each unit sets the variables documented on the
feature pages. The API unit needs all of them; the worker and beat units
only need the Celery, database, session, cache and OpenAI settings.

| Feature page | Variables |
|--------------|-----------|
| Foundation | `LOG_LEVEL`, `APP_NAME`, `DEBUG`, `DOCS_ENABLED`, `CORS_*`, `DATABASE_URL` |
| security.txt | `SECURITY_CONTACT`, `SECURITY_EXPIRES`, `SECURITY_PREFERRED_LANGUAGES`, ... |
| OAuth2 | `OAUTH2_ISSUER`, `OAUTH2_SWAGGER_CLIENT_ID`, `OAUTH2_CLIENT_ID`, `OAUTH2_CLIENT_CACHE_TTL`, `TOKEN_INTROSPECTION_CACHE_TTL`, `REDIS_URL` |
| Rate limiting | `RATE_LIMIT_*`, `SESSION_CREATE_*` |
| Sessions, cache and chat | `SESSION_REDIS_*`, `SESSION_COOKIE_*`, `CONVERSATION_*`, `CELERY_*` |
| Knowledge base, prompts, LLM | `RAG_*`, `PROMPT_CACHE_*`, `OPENAI_MODEL` |

The worker may use a cheaper `OPENAI_MODEL` than the API, since background
work is cost-sensitive.

### Secrets

Two values are secrets and are never written in the environment file. They
are delivered with systemd credentials (encrypted with `systemd-creds`,
loaded with `LoadCredentialEncrypted`), which the application reads from
`$CREDENTIALS_DIRECTORY` before falling back to the environment:

- `OPENAI_API_KEY`
- `OAUTH2_CLIENT_SECRET`

### Known mismatch

The production environment files still define `OAUTH2_CLIENT_REDIS_URL`,
which this application does not read: the token introspection and exchange
caches use `REDIS_URL` and stay disabled while it is empty. Define
`REDIS_URL` (and optionally `REDIS_KEY_PREFIX`) to enable them; the effect of
leaving it empty is one introspection request per authenticated call.

## Ansible

The `ansible/` collection of this repository provisions hosts (users,
security, PostgreSQL, Redis, nginx, certificates). It does not yet contain a
role that deploys this application, so the three units above are currently
installed by the production inventory outside this repository.

## Verifying a deployment

```bash
curl -fsS https://<api-domain>/health
curl -fsS https://<api-domain>/.well-known/security.txt
systemctl status backend backend-worker backend-beat
```
