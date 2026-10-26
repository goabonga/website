# Documents

Documents are the knowledge entries stored in a collection. Adding a document
generates its vector embedding with the OpenAI embeddings API and stores the
content, the embedding and some accounting fields in PostgreSQL (pgvector).

## Endpoints

All endpoints require a bearer token ([OAuth2
authentication](02-authentication.md)) and are tagged `Documents` in the public
OpenAPI document.

| Method | Path | Scope | Description |
| --- | --- | --- | --- |
| `POST` | `/api/v1/collections/{collection}/documents` | `documents:write` | Add 1 to 100 documents in one request; embeddings are requested in a single batch. Returns `201` with the created documents. |
| `POST` | `/api/v1/collections/{collection}/documents/single` | `documents:write` | Add one document. Returns `201`. |
| `GET` | `/api/v1/collections/{collection}/documents` | `documents:read` | List the documents of a collection (`offset`, `limit`, newest first). |
| `GET` | `/api/v1/documents/{document_id}` | `documents:read` | Get a document by id. |
| `DELETE` | `/api/v1/collections/{collection}/documents/{document_id}` | `documents:write` | Delete a document (`204`). |

`{collection}` is the UUID or the slug of the collection. The collection is
resolved inside the tenant of the request (`X-Tenant-ID` header, or the
default organization of the user, see authentication), so these endpoints
address the collections of that tenant. An unknown collection or document
answers `404`; an empty `content`, a body without documents or a batch of more
than 100 documents answers `422`.

### Payloads

`DocumentCreate`: `content` (required, at least one character), `metadata`
(free-form object, default `{}`), `source_type` (up to 50 characters) and
`source_ref` (up to 500 characters). `DocumentsCreate` wraps a `documents`
list.

`DocumentResponse`: `id`, `collection_id`, `content`, `metadata`,
`source_type`, `source_ref`, `created_at`, `updated_at`. The embedding itself
is never returned.

## What is stored

For each document `DocumentService` stores:

- `content_hash`: SHA-256 of the content, indexed, used to detect duplicates
  (`exists_by_hash`);
- `content_size`: size of the content in UTF-8 bytes;
- `embedding_size`: estimated size of the embedding (4 bytes per dimension),
  which feeds storage accounting;
- the embedding (`vector(1536)`), indexed with HNSW for cosine similarity.

The `document_count` of the collection is incremented when documents are added
and decremented when one is deleted. `delete_by_collection` removes every
document of a collection.

## Embeddings

`knowledge.services.embeddings.EmbeddingService` wraps the asynchronous OpenAI
client. `embed_text` embeds one text and `embed_texts` embeds a batch in one
call, re-ordering the results by index; both pass the configured model and
dimensions. `get_embedding_service()` returns a process-wide singleton.

## Settings

| Variable | Default | Description |
| --- | --- | --- |
| `OPENAI_API_KEY` | empty | OpenAI API key. Read through `get_credential`, so it can come from a systemd credential. |
| `EMBEDDING_MODEL` | `text-embedding-3-small` | Embedding model. |
| `EMBEDDING_DIMENSION` | `1536` | Dimensions requested from the API; must match the `vector(1536)` column. |

## Tests

pytest:

- `test_documents.py`: the five endpoints with mocked session,
  authentication and embedding service: scopes, validation, missing
  collection or document.
- `unit/test_document_service.py`: hashing and sizing, create, batch create,
  get, list, delete, deletion by collection and duplicate detection.
- `unit/test_embeddings_service.py`: single and batch embedding, ordering and
  the singleton.
- `unit/test_schemas.py`: `DocumentCreate` and `DocumentsCreate` validation.

behave (`features/documents.feature`): the real `DocumentService` runs over an
in-memory store with a deterministic embedder, so hashing, sizing and the
embedding calls are exercised.

- Add a single document
- Add several documents in one embedding batch
- List the documents of a collection
- Get a document by id
- Delete a document
- Documents of an unknown collection are not found
- Empty content is rejected
- Reading documents requires the read scope
- Writing documents requires the write scope
