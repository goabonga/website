# Knowledge base

Retrieval-augmented generation needs somewhere to retrieve from. The
knowledge base stores question and answer entries with an OpenAI embedding
in PostgreSQL (pgvector) and finds the entries closest in meaning to a
query.

## Data model

| Table | Model | Columns |
|-------|-------|---------|
| `knowledge_namespaces` | `KnowledgeNamespace` | `id`, `slug` (unique), `name`, `description`, `required_scopes` (array), `is_public`, `metadata`, `created_at`, `updated_at` |
| `knowledge_base` | `KnowledgeEntry` | `id`, `namespace_id` (foreign key, `SET NULL` on delete), `question`, `answer`, `embedding` (`vector(1536)`), `metadata`, `status`, `validation_details`, `created_at`, `updated_at` |

`status` is one of the `KnowledgeEntryStatus` values `pending`,
`validating`, `accepted` (the default), `rejected` and `needs_review`. The
semantic search does not filter on it.

### Namespace access

`KnowledgeNamespace.is_accessible(user_scopes)` decides who may see a
namespace. `user_scopes` is `None` for anonymous callers.

| Namespace | Anonymous | Authenticated |
|-----------|-----------|---------------|
| Public, no required scopes | yes | yes |
| Private, no required scopes | no | no |
| With required scopes | no | only if the user holds all of them |

## EmbeddingService

`EmbeddingService` wraps the OpenAI embeddings API with the model from
`RAG_EMBEDDING_MODEL`: `generate(text)` returns one vector and
`generate_batch(texts)` one call for many texts (an empty list makes no call).
Vectors have 1536 dimensions.

## KnowledgeBase

`KnowledgeBase(session)` owns an `EmbeddingService`.

| Method | Behaviour |
|--------|-----------|
| `search(query, limit, threshold, user_scopes, namespace_slug)` | Embed the query and run a cosine-similarity query (`1 - (embedding <=> :embedding)`), best first. Entries below `threshold` are dropped. Without `namespace_slug`, only entries without a namespace or in a namespace accessible to `user_scopes` are searched. Each result has `id`, `question`, `answer`, `metadata`, `namespace` and `similarity` |
| `add(question, answer, metadata, namespace_slug)` | Embed the question and insert an entry; an unknown namespace slug is logged and the entry gets no namespace |
| `add_batch(entries, namespace_slug)` | Same with a single batch embedding call |
| `get(id)`, `delete(id)` | Read or delete an entry |
| `update_embedding(id)` | Recompute the embedding of an entry |
| `create_namespace(...)`, `get_namespace_by_slug(slug)`, `list_namespaces(user_scopes)` | Namespace management; the listing is filtered by access and ordered by name |

The search uses PostgreSQL operators, so it needs the `vector` extension and
cannot run on SQLite; it is tested against a mocked session.

## Settings

| Variable | Default | Description |
|----------|---------|-------------|
| `OPENAI_API_KEY` | empty | OpenAI key; read from `$CREDENTIALS_DIRECTORY/OPENAI_API_KEY` first, then the environment |
| `RAG_EMBEDDING_MODEL` | `text-embedding-3-small` | Embedding model |
| `RAG_SIMILARITY_THRESHOLD` | `0.7` | Minimum similarity of a result |
| `RAG_MAX_RESULTS` | `5` | Default number of results |

## Tests

- pytest: `tests/rag/test_embeddings.py`, `tests/rag/test_knowledge_base.py`,
  `tests/models/test_knowledge.py` and the defaults and credential tests in
  `tests/test_config.py`.
- behave: `features/knowledge_base.feature` ("A public namespace is visible
  to everybody", "A private namespace without required scopes is never
  exposed", "A private namespace is opened by its required scope", "Required
  scopes must all be granted", "Search returns the best entries with their
  similarity", "Search without a match returns nothing"). The embedding
  service and the database are replaced by mocks.
