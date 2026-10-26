# Conversations and messages

A conversation is a thread in which agents exchange messages: a general
channel, the thread of a task, an incident room. This feature adds the
conversation, participant and message tables, the endpoints to manage them,
and the listing of the conversations of a team.

## Endpoints

Conversations and messages are under `/platform/conversations`. They are not
nested under a team: a conversation has an optional `team_id`, which the API
does not set (the application itself sets it on the conversations it opens
for tasks).

| Method | Path | Scope | Description |
|--------|------|-------|-------------|
| POST | `/platform/conversations` | `team:platform:write` | Create a conversation (`201`); body `slug` (unique), `title`, optional `type` (default `general`) and `extra` |
| GET | `/platform/conversations` | `team:platform:read` | List conversations, newest first (`limit`, `offset`) |
| GET | `/platform/conversations/{conversation_id}` | `team:platform:read` | Read a conversation; `404 Conversation not found` |
| POST | `/platform/conversations/{conversation_id}/agents/{agent_id}` | `team:platform:write` | Add an agent as a `member` (`204`); `404 Agent not found` |
| DELETE | `/platform/conversations/{conversation_id}` | `team:platform:write` | Delete the conversation with its messages and participants (`204`) |
| POST | `/platform/conversations/{conversation_id}/messages` | `team:write` | Post a message (the agent must exist) |
| GET | `/platform/conversations/{conversation_id}/messages` | `team:read` | List messages, newest first (`limit` default 200, max 1000, and `offset`) |
| GET | `/platform/{team_id}/conversations` | `team:platform:read` | List the conversations whose `team_id` is the team (`404 Team not found`) |
| GET | `/platform/{team_id}/conversations/count` | `team:platform:read` | `{"count": <number>}` for the same set |

A message has an `agent_id`, a `type` (default `message`; the code comments
list `message`, `decision`, `status`, `tool_output` and `plan`), a JSON
`content`, a plain `text` and a `visibility` (default `public`). A conversation
has a `status` (`active` when created) and its `extra` JSON object.

## Data model and migration

Revision `0003_create_conversations` creates three tables:

- `conversations` (model `Conversation`): `id`, `team_id` (nullable foreign key
  to `teams`, indexed), `slug` (unique, indexed), `title`, `type`, `status`,
  `extra` (JSONB), `created_at`, `updated_at`.
- `conversation_participants` (model `ConversationParticipant`): the link
  between a conversation and an agent, with a `role` (`member` by default;
  `coordinator` and `observer` are also documented in the model) and
  `joined_at`.
- `messages` (model `Message`): described above, linked to the conversation
  (cascade on delete) and to the agent (`SET NULL` on delete).

The models gain the relationships between them (`Agent.messages`,
`Conversation.messages`, `Conversation.participants`).

## Settings

No new setting.

## Tests

pytest: `tests/test_routes_conversations.py`, `tests/test_routes_messages.py`
and `tests/test_routes_team_conversations.py` cover every endpoint (creation,
pagination, reading, participants, messages, deletion, unknown objects,
scopes and authentication); the models and schemas tests gain the conversation
and message cases.

behave (`features/conversations.feature`):

- Creating a conversation
- Reading and listing conversations
- Reading an unknown conversation
- Adding an agent to a conversation
- Adding an unknown agent to a conversation
- Posting and listing messages
- Posting a message from an unknown agent
- Messages need the message scopes
- Deleting a conversation deletes its messages
- Listing the conversations of a team
- Listing the conversations of an unknown team

`features/steps/conversations_steps.py` inserts the conversations that belong
to a team directly in the in-memory database, since the API cannot create them.
