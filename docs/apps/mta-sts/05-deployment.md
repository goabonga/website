# Running and deployment

This page covers how the service is run locally and how the
`goabonga.website` Ansible collection deploys it.

## Local development

```bash
uv sync --package mta-sts
uv run --package mta-sts uvicorn mta_sts.main:app --reload --port 8000
curl http://127.0.0.1:8000/.well-known/mta-sts.txt

# tests (no network, no infrastructure)
uv run --package mta-sts pytest apps/mta-sts
uv run --package mta-sts behave apps/mta-sts/features

# lint and type-check
uv run ruff check apps/mta-sts
uv run ruff format --check apps/mta-sts
uv run mypy apps/mta-sts/src
```

`gunicorn` and `uvicorn[standard]` are the only dependencies that the code
does not import: they are the servers that run `mta_sts.main:app`.

## Components

The service is a single web process. There is no worker, no beat scheduler,
no Postgres and no Redis, and it keeps no state on disk.

## Deployment

The application is deployed under the catalog key `mta_sts`:

- type `gunicorn`, module `mta_sts.main:app`, one worker using
  `uvicorn.workers.UvicornWorker`, bound to a Unix socket behind nginx,
- an nginx virtual host for the `mta-sts.<domain>` host name with a Let's
  Encrypt certificate (HTTP-01 challenge) and a health check on `/health`,
- a hardened systemd unit and an environment file (mode `0600`) holding
  `APP_NAME`, `MTA_STS_MODE`, `MTA_STS_MAX_AGE` and `MTA_STS_MX`; the
  deployment overrides the `MTA_STS_MX` default with the actual MX host of
  the mail server,
- no secret.

Systemd captures the two logging streams described in
[Dual-stream logging](02-logging.md) in separate files.

## Dependencies on other applications

None. The MX host named in the policy must match the mail server that
actually receives the domain mail; the service never calls another
application.
