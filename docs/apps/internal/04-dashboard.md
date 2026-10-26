# Admin dashboard and chat history

The landing page and the first database-backed feature. The dashboard shows chat
statistics, and the conversation pages let operators browse and delete the chat history
stored by the platform's chat backend. This feature introduces the database layer
(`internal.database`): an async SQLAlchemy engine and session factory, the `get_db`
dependency, and a synchronous engine for background tasks.

## What it adds

| Module | Role |
| --- | --- |
| `internal/database.py` | Database configuration with SQLAlchemy async support. |
| `internal/models/__init__.py` | Database models for internal application. |
| `internal/models/conversation.py` | Conversation and message models for chat history (read-only access to fastapi-api db). |
| `internal/services/auth_client.py` | HTTP client for auth API (auth.goabonga.com). |
| `internal/routes/admin.py` | Admin routes for HTML pages - Chat History CRUD. |

It also ships 3 Jinja2 template(s) under `internal/templates/` (packaged with the wheel).

## Endpoints

| Method | Path | Required scope | Description |
| --- | --- | --- | --- |
| GET | / | `conversations:read` | Admin dashboard with chat statistics. |
| GET | /conversations | `conversations:read` | List all conversations with pagination and search. |
| GET | /conversations/{conversation_id} | `conversations:read` | View conversation detail with all messages. |
| POST | /conversations/{conversation_id}/delete | `conversations:delete` | Delete a conversation and all its messages. |
| POST | /conversations/bulk-delete | `conversations:delete` | Delete multiple conversations and all their messages. |

The dashboard asks the authorization server for `conversations:read`, `:write` and `:delete`
together with `analytics:read`, `vpn:admin` and `billing:read`; the list and detail pages ask for the same
set without `analytics:read`. This way the navigation and the buttons match what the user is allowed to do.
Deletion needs `conversations:delete`.

## Pages

- **Dashboard** (`/`): total conversations and messages, authenticated versus anonymous
  conversations (anonymous means no user but a session id), the five most recently
  updated conversations, and - if the user holds `analytics:read` - the 30-day
  analytics overview from the analytics feature (an unavailable analytics service
  is only logged).
- **Conversation list** (`/conversations`): 20 per page, newest first, with a message
  count. `search` accepts a user UUID (exact match on the owner) or any other text
  (partial, case-insensitive match on the session id); `type` filters
  `authenticated` or `anonymous` conversations.
- **Conversation detail** (`/conversations/{id}`): every message in order, and the
  owner's name and e-mail fetched from the authorization server. An unknown id renders the list with a
  "Conversation not found." banner.
- **Deletion**: single and bulk deletes redirect back to the list with a `success` or
  `error` query parameter, which the list shows. The list sends the selection of a bulk delete as one
  comma-separated `conversation_ids` value; the route also accepts repeated values. Messages go with their conversation.
- **Message text**: the detail page carries the text of every message, escaped by the server, and
  renders it as markdown when the CDN libraries load (`admin/_markdown.html`). Raw HTML in a message is shown as
  text and only `http`, `https` and `mailto` links and images are kept, because the messages come from visitors.

## Auth client

`internal.services.auth_client.AuthClient` (instance `auth_client`) resolves a user id
into a `UserInfo` (id, e-mail, name, active flag, creation date) by calling the
authorization server's admin API with a client-credentials token for the
`users:read` scope (cached until 30 seconds before expiry). Any failure - no issuer
configured, token error, unknown user, non-200 answer - is logged and yields `None`,
so the detail page simply shows the raw user id.

## Database access

`DATABASE_URL` accepts the usual `postgresql://` form; `get_async_database_url` rewrites it
for the `asyncpg` driver and `get_sync_database_url` for `psycopg` (used by Celery
tasks later on). Sessions do not expire objects on commit.

## Settings

Read from environment variables (or a `.env` file) by `internal.config.Settings`.

| Variable | Default | Notes |
| --- | --- | --- |
| `DATABASE_URL` | `'postgresql://localhost/app'` | Database (shared with backend - contains chat history) |

`DATABASE_URL` points at the shared PostgreSQL database; in production it is typically a Unix-socket URL with peer authentication.

## Data model

The conversation tables belong to the platform's chat backend, which shares its
database with this application; `internal` only reads and deletes. Deleting a conversation
removes its messages through the foreign key (`ON DELETE CASCADE`).

**`Conversation`** maps the `conversations` table: `id`, `user_id`, `session_id`, `title`, `created_at`, `updated_at`.

**`Message`** maps the `messages` table: `id`, `conversation_id`, `role`, `content`, `created_at`.

This application ships no migrations: it never creates or alters tables.

## Tests

pytest:

- `tests/test_database.py`
- `tests/routes/test_admin.py`
- `tests/services/test_auth_client.py`
- `tests/routes/test_dashboard_sidebar.py`

The tests cover the URL conversion helpers, the session dependency, every handler of `routes/admin.py` and the auth client. The list route is tested for the flash messages it passes to its page, the bulk delete for a comma-separated selection, and the detail template for the escaping of message markup.

`tests/routes/test_dashboard_sidebar.py` opens every page of this feature through the application with its real templates (throw-away SQLite database, mocked service clients) and, for each scope combination, checks the sidebar: exactly the links the scopes permit, a single active link and the signed-in user.

Behave scenarios, run in-process with `uv run --package internal behave apps/internal/features` (`features/admin.feature`):

- View admin dashboard
- View admin dashboard unauthenticated
- List conversations when empty
- List conversations with data
- List conversations with search filter
- View conversation detail
- View conversation detail not found
- Delete a conversation
- Bulk delete conversations
- Bulk delete conversations with empty list
- Sidebar on the admin dashboard
- Sidebar on the conversations list
- Sidebar on the conversation detail
- Sidebar on the missing conversation

Database-backed scenarios run against a throw-away SQLite file created by
`features/environment.py`: the engine is swapped in through a `get_db` dependency
override, PostgreSQL-only column types are mapped to portable ones and foreign keys are
enforced, so the cascade delete is exercised for real. Every table is emptied before each scenario.

Browser scenarios, run in Chromium against the application served on a local socket (`features/browser/admin.feature`, `uv run --package internal --group dev behave apps/internal/features -t @browser`):

- The dashboard summarizes the conversations
- The dashboard hides the analytics from a user without the analytics scope
- The dashboard links to the analytics and to the conversations
- The dashboard opens a recent conversation
- A user without conversation scopes gets the access denied page
- The access denied page offers to log out
- The list shows the conversations with their number of messages
- An empty history says so
- Searching narrows the list to the matching session
- Filtering by type keeps only anonymous or authenticated conversations
- The list is paginated
- The search is kept when moving to the next page
- The detail shows the owner and the messages
- A conversation that does not exist is reported
- Deleting a conversation asks for a confirmation and reports the success
- Dismissing the confirmation keeps the conversation
- A user who cannot delete does not see the delete button
- Selected conversations are deleted in bulk
- Clearing the selection hides the bulk actions

The conversations and messages live in the throw-away SQLite database shared with the server thread. The scenarios cover the dashboard and its optional analytics block, the search, the type filter and the pagination of the list (a search containing `&` stays intact on the next page), the message markup shown as text, the delete confirmations (accepted and dismissed), the bulk selection and the flash messages the delete routes redirect with.
