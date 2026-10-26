# Semantic search

Semantic search embeds the query with the same model as the documents and
ranks the stored documents by vector similarity, directly in PostgreSQL with
pgvector.

## Endpoints

Both endpoints require the `collections:search` scope and are tagged `Search`
in the public OpenAPI document.

| Method | Path | Description |
| --- | --- | --- |
| `POST` | `/api/v1/search` | Search across the collections of the tenant, or across the collections listed in `collection_ids`. |
| `POST` | `/api/v1/search/collections/{collection}` | Search inside one collection (UUID or slug); `collection_ids` is overridden. |

Collections are resolved inside the tenant of the request, like the
[documents](04-documents.md) endpoints. Ids or slugs that do not resolve are
ignored; when nothing remains the response is empty with `200`.

### Request

| Field | Default | Description |
| --- | --- | --- |
| `query` | required | Text to search for (at least one character). |
| `collection_ids` | all collections | Collection UUIDs or slugs. |
| `top_k` | `10` | Maximum number of results, between 1 and 100. |
| `threshold` | `0.7` | Minimum similarity, between 0 and 1. |
| `distance_type` | `cosine` | `cosine`, `l2` or `inner_product`. |
| `filters` | none | Metadata filters (accepted by the schema). |
| `include_content` | `true` | When `false`, results carry an empty `content`. |

### Response

`SearchResponse` holds `query`, `total_results` and `results`; each result has
`document_id`, `collection_id`, `collection_slug`, `content`, `score` and the
document `metadata`. Results are ordered by decreasing score.

### Distance types

| Type | pgvector operator | Similarity |
| --- | --- | --- |
| `cosine` | `<=>` | `1 - distance` (recommended with OpenAI embeddings) |
| `l2` | `<->` | `1 / (1 + distance)` |
| `inner_product` | `<#>` | negated inner product (vectors should be normalized) |

The query uses the HNSW cosine index created on `documents.embedding` for the
`cosine` type.

## Settings

| Variable | Default | Description |
| --- | --- | --- |
| `DEFAULT_SIMILARITY_THRESHOLD` | `0.7` | Declared in the settings. |
| `DEFAULT_SEARCH_LIMIT` | `10` | Declared in the settings. |
| `MAX_SEARCH_LIMIT` | `100` | Declared in the settings. |

These three values are not read by the code yet: the defaults and limits of a
request are the ones of the `SearchRequest` schema above. The query embedding
uses the `OPENAI_API_KEY`, `EMBEDDING_MODEL` and `EMBEDDING_DIMENSION`
settings described in the documents page.

## Tests

pytest:

- `test_search_routes.py`: both endpoints with a mocked service: scope,
  validation and response shape.
- `unit/test_search_service.py`: query embedding, collection resolution,
  empty results, the three distance types, `include_content` and
  `search_collection`.
- `unit/test_schemas.py`: `SearchRequest` defaults and bounds.

behave (`features/search.feature`): the route, validation and response model
are real; the pgvector ranking is replaced by an in-memory cosine similarity
over a bag-of-words embedding, because the ranking SQL needs PostgreSQL. The
generated SQL itself is covered by the pytest suite.

- Search across every collection ranks the best match first
- The similarity threshold filters weak matches
- top_k limits the number of results
- Search a single collection by slug
- Searching an unknown collection returns no result
- Content can be left out of the results
- An empty query is rejected
- top_k above the maximum is rejected
- Searching requires the search scope
