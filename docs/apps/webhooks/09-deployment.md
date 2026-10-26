# Running and deployment

This page covers how the gateway is run locally and how it is deployed on the
platform.

## Local development

```bash
uv sync --package webhooks
BREVO_ENABLED=true BREVO_INTERNAL_API_URL=http://127.0.0.1:9000 \
  uv run --package webhooks uvicorn webhooks.main:app --reload --port 8001
curl http://127.0.0.1:8001/health

# tests (no network, no infrastructure)
uv run --package webhooks pytest apps/webhooks
uv run --package webhooks behave apps/webhooks/features

# lint and type-check
uv run ruff check apps/webhooks
uv run ruff format --check apps/webhooks
uv run mypy apps/webhooks/src
```

All providers are disabled by default: enable the ones you need with their
`<PROVIDER>_ENABLED` variable and point them to an internal API with
`<PROVIDER>_INTERNAL_API_URL` or `<PROVIDER>_INTERNAL_API_SOCKET`. A route
that is enabled but not wired to an internal API answers 503.

`gunicorn` and `uvicorn[standard]` are the only dependencies that the code
does not import: they are the servers that run `webhooks.main:app`.

## Components

The gateway is a single web process. There is no worker, no beat scheduler,
no Postgres and no Redis, and it keeps no state on disk besides logs.

## Deployment

The application is deployed with the `python_app` role of the platform's
Ansible setup, as a catalog entry of type `gunicorn`:

- module `webhooks.main:app`, one worker using
  `uvicorn.workers.UvicornWorker`, bound to a Unix socket behind nginx,
- an nginx virtual host for the public `webhooks.<domain>` host name with a
  Let's Encrypt certificate (HTTP-01 challenge) and a health check on
  `/health`; the host must be publicly reachable so that providers can POST
  to it,
- a hardened systemd unit and an environment file (mode `0600`),
- the service user is added to the groups of the internal services it
  forwards to, so it can write to their Unix sockets (for example the mail
  sending and billing services),
- logs written by systemd to an output log (stdout) and an error log
  (stderr), see [Dual-stream logging](02-logging.md).

Typical environment of a deployment:

| Variable | Purpose |
| --- | --- |
| `APP_NAME`, `LOG_LEVEL`, `DOCS_ENABLED` | Application settings |
| `OAUTH2_TOKEN_URL`, `OAUTH2_CLIENT_ID` | Token endpoint and client of the [OAuth2 client credentials](03-oauth2.md) |
| `BREVO_ENABLED`, `BREVO_INTERNAL_API_SOCKET` | [Brevo](04-brevo.md) events forwarded to the mail sending service over its Unix socket |
| `STRIPE_ENABLED`, `STRIPE_INTERNAL_API_SOCKET` | [Stripe](06-stripe.md) events forwarded to the billing service over its Unix socket |
| `SES_ENABLED`, `SENDGRID_ENABLED`, `GITHUB_ENABLED` | The [SES](05-ses.md), [SendGrid](07-sendgrid.md) and [GitHub](08-github.md) providers can be left disabled |

Secrets (`OAUTH2_CLIENT_SECRET`, and when used the Brevo, SendGrid and GitHub
verification secrets and the internal API tokens) are delivered as systemd
encrypted credentials and read from `CREDENTIALS_DIRECTORY` by
`webhooks.config.get_credential`. They never appear in the environment file.

Debug logging and the OpenAPI documentation are enabled in a development
deployment; set `LOG_LEVEL=INFO` and `DOCS_ENABLED=false` for production.

## Dependencies on other applications

The gateway calls other applications but is not called by them:

- the mail sending service, for Brevo (and SES/SendGrid) events,
- the billing service, for Stripe events (it verifies the Stripe signature),
- the authentication service, whose token endpoint issues the OAuth2 access
  tokens used for those calls.
