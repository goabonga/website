# Memory

The memory of a team is a list of entries: short texts that users and agents
want to remember, each stored with an embedding vector so that they can be
searched by meaning. This feature adds the memory table (with the PostgreSQL
`pgvector` extension), the endpoints to manage the entries, the embedding
service and a small query service.

## Endpoints

All routes are under `/platform/{team_id}/memory` and check that the team
exists (`404 Team not found`). Entries are scoped to the team in the URL: an
entry of another team is reported as `404 Memory entry not found`.

| Method | Path | Scope | Description |
|--------|------|-------|-------------|
| GET | `/platform/{team_id}/memory` | `team:platform:read` | List the entries of the team, newest first (`limit`, `offset`) |
| POST | `/platform/{team_id}/memory` | `team:platform:write` | Create an entry (`201`); body `content` (required), optional `agent_id`, `conversation_id` and `extra` |
| PATCH | `/platform/{team_id}/memory/{entry_id}` | `team:platform:write` | Change the `content` and/or the `extra` metadata |
| DELETE | `/platform/{team_id}/memory/{entry_id}` | `team:platform:write` | Delete an entry (`204`) |

The embedding is never part of the response. It is computed when an entry is
created and again when its content changes; changing only `extra` keeps it.

## Embeddings

`team.services.embeddings.generate_embedding(text)` calls the OpenAI
embeddings API with the model `text-embedding-3-small` and 1536 dimensions.
`generate_embeddings_batch(texts)` does the same for several texts in one call.
When `OPENAI_API_KEY` is empty both functions log a warning and return zero
vectors instead of failing, so that the platform works (without useful
search) in an environment that has no key.

## Data model and migration

Revision `0004_create_memory_entries` enables the extension (`CREATE
EXTENSION IF NOT EXISTS vector`), creates the table `memory_entries` (model
`MemoryEntry`) and an `ivfflat` cosine index on the embedding:
`id`, `team_id`, `agent_id` and `conversation_id` (optional foreign keys,
cascade on delete), `content`, `extra` (JSONB), `embedding` (`vector(1536)`)
and `created_at`. The database user that runs the migration must be allowed
to create the extension, and the PostgreSQL server must have `pgvector`
installed (the `compose.yml` image does).

`team.services.MemoryService` returns the most recent entries of a team
(`get_recent_entries(team_id, limit=50)`) and the entries of an agent
(`get_agent_memory(agent_id, limit=50)`).

## Settings

| Variable | Default | Description |
|----------|---------|-------------|
| `OPENAI_API_KEY` | empty | OpenAI key used for the embeddings; read as a credential (see [Foundation](01-foundation.md)), so it can come from the systemd credentials directory |

## Tests

pytest: `tests/test_routes_memory.py` covers the four endpoints,
`tests/test_services_embeddings.py` covers the OpenAI calls (mocked client),
the zero vector fallback and the batch function, `tests/test_services_memory.py`
covers the query service, and the settings, models and schemas tests gain the
memory cases.

behave (`features/memory.feature`), with a fake embedding model that returns
`[length of the text, 0, 0]` so that the scenarios can check which text was
embedded:

- Creating a memory entry computes its embedding
- Updating the content computes a new embedding
- Updating only the metadata keeps the embedding
- Listing the memory of a team
- Deleting a memory entry
- An entry cannot be changed through another team
- Memory of an unknown team
- Creating a memory entry needs the write scope
- Without an OpenAI key the embedding is a zero vector
- The memory service returns the most recent entries of a team and of an agent

The `vector` column is stored as JSON in the in-memory SQLite database of the
scenarios; similarity queries need PostgreSQL and are not exercised by them.
