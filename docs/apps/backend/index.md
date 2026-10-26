# backend

The main API service of the platform, a FastAPI application served at the
public API domain. The workspace member is `apps/backend` (distribution
`backend`, import package `backend`, ASGI application
`backend.main:app`).

The service is built feature by feature. Each page below documents one
feature: what it does, how it is configured, how it is tested.

## Features

1. [Application foundation](01-foundation.md): settings, logging, database
   base, FastAPI application and the `/health` probe.
2. [security.txt endpoint](02-security-txt.md): RFC 9116 disclosure file built from settings.
3. [OAuth2 token authentication](03-oauth2-authentication.md): JWT and opaque token validation, scopes.
4. [Redis rate limiting](04-rate-limiting.md): per-user and per-address sliding window, session creation budget.
5. [Conversations](05-conversations.md): conversation, message and usage models, `ChatService`.
6. [Anonymous sessions](06-anonymous-sessions.md): cookie sessions and the unified chat context.
7. [Conversation cache and background sync](07-conversation-cache.md): write-behind Redis cache and the Celery sync task.
8. [Knowledge base](08-knowledge-base.md): pgvector entries, namespaces with scope access and semantic search.
9. [Scoped system prompts](09-system-prompts.md): versioned prompts selected by OAuth2 scopes and cached in Redis.
10. [LLM client and tools](10-llm-and-tools.md): OpenAI client and the scope-aware tool registry.
11. [Chat orchestration and streaming](11-chat-orchestration.md): tool routing, streamed answers and SSE events.
12. [Chat endpoint](12-chat-endpoint.md): `POST /api/v1/chat`, history mode, cookies and rate limiting.

## Running the tests

Run every command from the repository root.

```bash
# Unit tests
uv run --package backend --group dev pytest apps/backend

# Behave scenarios (in-process, no external services)
uv run --package backend --group dev behave apps/backend/features
```
