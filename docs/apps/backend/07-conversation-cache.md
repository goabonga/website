# Conversation cache and background sync

Chat writes must not wait for PostgreSQL. `ConversationCache` is a
write-behind cache: conversations and messages are written to Redis and the
conversation is flagged "dirty"; a periodic Celery task copies dirty
conversations to the database.

## ConversationCache

`ConversationCache(db)` talks to the Redis database `SESSION_REDIS_URL`.

| Key | Content |
|-----|---------|
| `conv:<uuid>` | JSON document: id, owner, title, messages, timestamps (TTL `CONVERSATION_CACHE_TTL`) |
| `conv:dirty:<uuid>` | Marker set whenever the cached copy is ahead of PostgreSQL |

| Method | Behaviour |
|--------|-----------|
| `get(id)` | Read-through: Redis first (TTL refreshed), otherwise load from PostgreSQL with its messages and cache it |
| `create(user_id, session_id, title)` | Insert in PostgreSQL immediately, then cache the document |
| `add_message(id, role, content)` | Append to the cached document and mark it dirty; `ValueError` if the conversation does not exist |
| `update_title(id, title)` | Change the cached title and mark dirty; `None` if not found |
| `get_dirty_conversations()` | Scan `conv:dirty:*` and return the ids |
| `sync_to_db(id)` | Create or update the conversation row, insert the messages whose id is not yet stored, commit, clear the flag; returns `False` (and clears the flag) when the cached copy has expired |
| `delete(id)` | Delete from PostgreSQL and Redis |
| `invalidate(id)` | Delete from Redis only, so the next read reloads from PostgreSQL |

A cached conversation that expires before it is synced is lost, so the sync
interval must stay well below the cache TTL.

## Celery application

`backend.celery.celery_app` uses the broker and result backend from the
settings, JSON serialisation, UTC and a 300 second hard time limit. Tasks
live in a dedicated queue called `backend`, so that several applications can
share one Redis. The task module `backend.tasks.sync_conversations` is
included explicitly.

| Task | Schedule | Role |
|------|----------|------|
| `sync_dirty_conversations` | every `CONVERSATION_SYNC_INTERVAL` seconds (expires after the same delay) | Sync each dirty conversation; one failing conversation is logged and does not stop the others; returns the number synced |

Run the processes from the repository root:

```bash
uv run --package backend celery -A backend.celery:celery_app worker -Q backend
uv run --package backend celery -A backend.celery:celery_app beat
```

## Settings

| Variable | Default | Description |
|----------|---------|-------------|
| `CELERY_BROKER_URL` | `redis://localhost:6379/0` | Celery broker |
| `CELERY_RESULT_BACKEND` | `redis://localhost:6379/0` | Celery result backend |
| `CONVERSATION_CACHE_TTL` | `1800` | Seconds a cached conversation lives |
| `CONVERSATION_SYNC_INTERVAL` | `30` | Seconds between two sync runs |

## Tests

- pytest: `tests/session/test_cache.py`, `tests/tasks/test_sync_conversations.py`,
  `tests/test_celery.py`.
- behave: `features/conversation_cache.feature` ("A new conversation is
  cached", "Adding a message marks the conversation dirty", "Syncing writes the
  messages to the database and clears the flag", "Invalidating removes the
  conversation from Redis only", "The sync task is scheduled by Celery
  beat"). Redis is replaced by an in-memory fake and the database by a mock,
  so no broker is needed.
