# Asterisk bot

Voice bot that bridges phone calls handled by Asterisk to the OpenAI
Realtime API. Asterisk streams the caller audio to this daemon over the
AudioSocket protocol; the daemon relays it to OpenAI and plays the
synthesized answer back to the caller.

The application is the workspace member `apps/asterisk` (distribution
`asterisk`, import package `asterisk`). It is a single asyncio daemon:
there is no HTTP API, no web server, no Celery worker and no Alembic
migration.

```
Asterisk (caller)  <--8 kHz PCM, TCP-->  AudioSocket server  <--24 kHz PCM, WebSocket-->  OpenAI Realtime
```

## Features

The application is documented feature by feature, in the order in which
each feature builds on the previous ones.

1. [Application foundation](01-foundation.md): package, settings and logging.
2. [AudioSocket server](02-audiosocket.md): the Asterisk-facing TCP server.
3. [Audio resampling](03-audio-resampling.md): 8 kHz to 24 kHz conversion and buffering.
4. [OpenAI Realtime client](04-openai-realtime.md): WebSocket client, tools and barge-in.
5. [Call handler](05-call-handler.md): per-call bridge, greeting, interruption and hangup.
6. [Knowledge base](06-knowledge-base.md): optional pgvector RAG tool.

## Testing

Each feature has pytest tests and a behave scenario file. Everything runs
in process: the telephony side (Asterisk, AudioSocket streams) and the
OpenAI side are replaced by fakes.

```bash
uv run --package asterisk --group dev pytest apps/asterisk
uv run --package asterisk --group dev behave apps/asterisk/features
```
