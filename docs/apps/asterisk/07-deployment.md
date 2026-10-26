# Deployment and operations

This page gathers what is needed to run the bot: local development, the
runtime layout and the integration with Asterisk. It adds no code.

## Local development

```bash
# install the member and the dev tools
uv sync --package asterisk

# run the daemon (OPENAI_API_KEY is needed for real calls)
uv run --package asterisk python -m asterisk.main

# optional local PostgreSQL with pgvector on port 5442
docker compose -f apps/asterisk/compose.yml up -d

# tests (no network, no database, no Asterisk needed)
uv run --package asterisk --group dev pytest apps/asterisk
uv run --package asterisk --group dev behave apps/asterisk/features

# lint
uv run --group dev ruff check apps/asterisk
uv run --group dev ruff format --check apps/asterisk
```

The compose file only starts the database of the knowledge base
(`pgvector/pgvector:pg16`, database `asterisk_bot_test`, port 5442). To use
it set, for example,
`DATABASE_URL=postgresql://asterisk_bot:asterisk_bot@localhost:5442/asterisk_bot_test`
and `RAG_ENABLED=true`; these credentials are local development values.

## Runtime shape

- A single long-running process: `python -m asterisk.main`. There is no
  HTTP interface, no reverse proxy, no TLS certificate, no Celery worker or
  beat scheduler, no Redis and no Alembic migration.
- The only listening socket is the AudioSocket TCP port (default
  `127.0.0.1:9092`). The protocol is unauthenticated: keep it on the
  loopback interface so that only the local Asterisk can reach it.
- Outbound connections: the OpenAI Realtime WebSocket (one per call), the
  OpenAI Embeddings API and PostgreSQL when RAG is enabled.
- The process stops gracefully on `SIGTERM` or `SIGINT`: the AudioSocket
  server is closed and the knowledge base pool is released. Calls in
  progress end with the process.
- Logs go to stdout (below `ERROR`) and stderr (`ERROR` and above), which
  fits `journald` or a redirect to log files.

## Secrets

`OPENAI_API_KEY` should not live in an environment file. When the service
is started by systemd with `LoadCredentialEncrypted=` (credential named
`OPENAI_API_KEY`), the key is read from `$CREDENTIALS_DIRECTORY`; the
plain environment variable is only the fallback for development. The
database URL, if it embeds a password, is also a secret: prefer a local
Unix socket with peer authentication, for example
`postgresql:///application?host=/var/run/postgresql`.

## Asterisk integration

Calls reach the bot through a dialplan context that answers, then opens
the AudioSocket connection and hangs up when it ends:

```ini
[audiosocket-bot]
exten => s,1,NoOp(Starting AudioSocket bot)
 same => n,Answer()
 same => n,AudioSocket(${UUID()},127.0.0.1:9092)
 same => n,Hangup()
```

The first argument of `AudioSocket()` is the call UUID (generated with
`${UUID()}`) and the second the address of the daemon. The context must be
included from `extensions.conf`, followed by an Asterisk reload.

## Production layout

The platform runs the bot on the same host as Asterisk, from a dedicated
unprivileged system user, as a systemd service:

- a virtualenv built from this workspace member, started with
  `python -m asterisk.main`;
- an environment file readable by the service user only, holding the
  non-secret settings of the earlier pages (`LOG_LEVEL`, `OPENAI_MODEL`,
  `OPENAI_VOICE`, `OPENAI_SYSTEM_PROMPT`, `GREETING_MESSAGE`, `RAG_*`,
  `DATABASE_URL`) and `AUDIOSOCKET_HOST` / `AUDIOSOCKET_PORT`;
- `OPENAI_API_KEY` as an encrypted systemd credential;
- the unit ordered `After=network.target asterisk.service` with
  `Wants=asterisk.service`, `Restart=always` and the usual systemd
  sandboxing options;
- when RAG is enabled, the shared PostgreSQL database with the `vector`
  extension available, reached through the local Unix socket.

The [python_app](../../ansible/roles/python_app.md) role of the Ansible
collection deploys this layout from the catalog of the `apps` playbook
([Deploying applications](../../ansible/05-deploying-apps.md)): enable
`asterisk` in `website_apps_enabled`. The component runs as the user
`asterisk-bot`, with the unit type `audiosocket` (`python -m asterisk.main`),
which sets `AUDIOSOCKET_HOST` and `AUDIOSOCKET_PORT` (`127.0.0.1:9092`) in
the unit and orders it after `asterisk.service`. It also:

- uses the shared `application` database, with the `vector` extension, and
  writes the non-secret settings (`LOG_LEVEL`, `OPENAI_MODEL`,
  `OPENAI_VOICE`, `RAG_*`) in the environment file;
- requires `OPENAI_API_KEY` in `website_secrets`
  ([Secrets](../../ansible/03-secrets.md)) and deploys it as an encrypted
  credential;
- writes the dialplan context `fastagi-bot` (the catalog name; the example
  above uses another one) in `extensions_asterisk-bot.conf`, includes it from
  `extensions.conf` and reloads Asterisk. The [asterisk](../../ansible/roles/asterisk.md)
  role must have run first, and the deployment stops when `extensions.conf`
  is missing.

Model, voice, prompts and RAG options are overridden per host through the
environment file; the defaults are listed in the settings tables of the
previous pages.

## Dependencies on other applications

None at runtime. The knowledge base may share the PostgreSQL database used
by other applications of the platform, and a local Asterisk instance is
required for real calls.
