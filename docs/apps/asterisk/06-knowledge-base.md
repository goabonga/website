# Knowledge base (RAG)

The knowledge base lets the bot answer from stored question/answer pairs
instead of improvising. It is optional and disabled by default. When
`RAG_ENABLED=true`, the model gets a `search_knowledge` tool and is
instructed to use it before answering.

## What it does

- `asterisk.knowledge_base.KnowledgeBase` keeps an `asyncpg` pool
  (1 to 5 connections) and uses the OpenAI Embeddings API to turn text
  into vectors.
- `search(query)` embeds the query and selects the closest rows by cosine
  distance (`embedding <=> $1::vector`), keeps those whose similarity
  (`1 - distance`) is at least `RAG_SIMILARITY_THRESHOLD`, and returns at
  most `RAG_MAX_RESULTS` `KnowledgeEntry` objects (`id`, `question`,
  `answer`, `similarity`). Errors are logged and give an empty list; so
  does a knowledge base that is not connected.
- `get_sample_questions(limit)` returns random stored questions.
- `add_entry`, `update_entry` and `delete_entry` manage the content. They
  are a Python API: the application exposes no command or endpoint to
  call them, so entries are loaded by your own script or directly in SQL
  (embeddings must then be computed with the same model).
- `get_knowledge_base()` returns the process-wide instance, created and
  connected on first use (`None` when RAG is disabled);
  `close_knowledge_base()` closes it. `shutdown()` in `asterisk.main`
  calls the latter when RAG is enabled.

### Effect on the call handler

When RAG is enabled `handle_call()`:

- declares the `search_knowledge(query)` function next to `hangup`;
- appends knowledge base instructions to the system prompt: always search
  before answering, answer only from the results, say that the question
  cannot be answered when nothing is found and suggest sample questions,
  and answer small talk (greetings, goodbye) normally;
- answers the tool call with
  `{"found": true, "results": [{"question", "answer", "confidence"}]}`
  or, when nothing matches,
  `{"found": false, "message": ..., "sample_questions": [...]}` (three
  random questions). If the knowledge base is unavailable the answer is
  `{"error": "Knowledge base not available"}`.

## Settings

| Variable | Default | Description |
| --- | --- | --- |
| `DATABASE_URL` | empty | PostgreSQL URL of the knowledge base |
| `RAG_ENABLED` | `false` | Enable the `search_knowledge` tool (`true`, case-insensitive) |
| `RAG_EMBEDDING_MODEL` | `text-embedding-3-small` | OpenAI embedding model |
| `RAG_SIMILARITY_THRESHOLD` | `0.7` | Minimum cosine similarity for a match |
| `RAG_MAX_RESULTS` | `3` | Maximum matches returned per search |

Embeddings use `OPENAI_API_KEY`, introduced with the call handler.

## Data model

There is no Alembic migration: the application manages its single table
itself. On connection, `_ensure_schema()` checks `information_schema` and,
if `knowledge_base` already exists (for instance created by another
application of the platform on a shared database), does nothing, so it
works with a role that is not the table owner. Otherwise it runs:

- `CREATE EXTENSION IF NOT EXISTS vector`
- table `knowledge_base`: `id SERIAL PRIMARY KEY`, `question TEXT`,
  `answer TEXT`, `embedding vector(1536)`, `created_at`, `updated_at`
- an `ivfflat` cosine index on `embedding` (`lists = 100`)

The dimension 1536 matches `text-embedding-3-small`; another embedding
model needs another table definition. The server needs the `vector`
extension (for example the `pgvector/pgvector` image).

## Dependencies

Adds `openai` (embeddings) and `asyncpg` to the project dependencies.

## Tests

PostgreSQL and the embeddings API are faked, nothing is contacted.

- pytest: `tests/test_knowledge_base.py` mocks the asyncpg pool and the
  OpenAI client and covers connection, schema creation and skipping,
  search (threshold, errors), samples, add/update/delete and the shared
  instance. `tests/test_call_handler.py` covers the RAG tool, the prompt
  and the tool call results, `tests/test_main.py` the shutdown, and
  `tests/test_config.py` the new settings.
- behave: `features/knowledge_base.feature` runs the real
  `KnowledgeBase` against `FakePostgres`, an in-memory database that
  understands its statements and ranks rows by cosine similarity of a
  bag-of-words embedding (`features/steps/fakes.py`). Scenarios: *The
  schema is created on first connection*, *An existing table is left
  untouched*, *Adding an entry stores its embedding*, *Search returns
  matching entries above the threshold*, *Search finds nothing when no
  entry is close enough*, *Search is limited to the maximum number of
  results*, *Search without a connection returns nothing*, *Updating and
  deleting entries*, *Sample questions* and the two shared-instance
  scenarios. `features/call_handler.feature` gains *RAG adds the knowledge
  search tool and its instructions*, *A question is answered from the
  knowledge base* and *An unanswered question returns sample questions*.
