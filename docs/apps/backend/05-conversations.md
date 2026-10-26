# Conversations

The persistent model of a chat: conversations, their messages and the usage
counters, plus `ChatService`, the only code that reads and writes them.

## Data model

All models derive from `backend.database.Base` and use PostgreSQL UUID
primary keys.

| Table | Model | Columns |
|-------|-------|---------|
| `conversations` | `Conversation` | `id`, `user_id` (nullable, indexed), `session_id` (nullable, indexed, 36 characters), `title` (255), `summary`, `created_at`, `updated_at`, `archived_at` (nullable, indexed) |
| `messages` | `Message` | `id`, `conversation_id` (foreign key, cascade delete, indexed), `role` (20), `content`, `created_at` |
| `usage_logs` | `UsageLog` | `id`, `user_id`, `conversation_id` (foreign key, cascade delete), `prompt_tokens`, `completion_tokens`, `model` (50), `created_at` |

A conversation is owned either by a user (`user_id`) or by an anonymous
session (`session_id`). Messages are ordered by `created_at`, and deleting a
conversation deletes its messages and usage logs.

## ChatService

`ChatService(session)` wraps an `AsyncSession` and commits after every
write.

| Method | Behaviour |
|--------|-----------|
| `create_conversation(user_id, session_id, title)` | Insert and return a conversation |
| `get_or_create_conversation(user_id, session_id)` | Return `(conversation, created)`; a user or session has at most one active (non-archived) conversation; without owner a throw-away conversation is created |
| `get_conversation(conversation_id, user_id, session_id)` | Load with messages, optionally restricted to an owner |
| `list_conversations(user_id, session_id, limit, offset)` | Most recently updated first; empty list without owner |
| `add_message(conversation_id, role, content)` | Insert a message |
| `get_conversation_history(conversation_id, limit)` | List of `{"role", "content"}` dicts in order |
| `update_title`, `update_summary` | Set the generated title or summary |
| `delete_conversation`, `reset_conversation` | Hard delete, by id or for an owner |
| `archive_conversation(user_id, session_id)` | Soft delete: set `archived_at`, keep the messages |
| `migrate_conversation(session_id, user_id)` | Give an anonymous conversation to a user, merging messages into the user's active conversation if one exists |

`backend.chat` exports `ChatService`.

## Tests

- pytest: `tests/chat/test_service.py` (every method with a mocked session)
  and `tests/models/test_conversation.py` (tables, columns, nullability,
  cascades and registration on `Base.metadata`). `tests/conftest.py` gains the
  conversation fixtures.
- behave: `features/conversation.feature` ("Creating a conversation for an
  anonymous session", "The active conversation is reused", "A conversation
  is created when none is active", "Messages are stored with their role",
  "History is returned as role and content pairs", "Archiving keeps the
  conversation but marks it"). The database session is a mock created in
  `features/environment.py`.
