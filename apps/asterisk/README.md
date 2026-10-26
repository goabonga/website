# asterisk

Voice bot bridging Asterisk phone calls to the OpenAI Realtime API.

It runs an AudioSocket TCP server for Asterisk, resamples the call audio
(8 kHz to 24 kHz and back), relays it to the OpenAI Realtime API over a
WebSocket, supports barge-in and a `hangup` tool, and can answer from an
optional pgvector knowledge base (RAG).

## Routes and scopes

The application serves no HTTP route and checks no scope or role. Its only network entry point is the AudioSocket TCP server that Asterisk connects to (`AUDIOSOCKET_HOST`, default `127.0.0.1`, and `AUDIOSOCKET_PORT`, default `9092`). The server does no authentication: access is limited by the address it listens on.

## Development

From the repository root:

```bash
uv sync --package asterisk
uv run --package asterisk python -m asterisk.main
uv run --package asterisk --group dev pytest apps/asterisk
uv run --package asterisk --group dev behave apps/asterisk/features
```

Settings come from environment variables (a `.env` file is loaded when
present). The optional `compose.yml` starts a local PostgreSQL with
pgvector on port 5442 for manual experiments with the knowledge base.

Documentation: `docs/apps/asterisk/`.
