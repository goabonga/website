# knowledge

Vector storage and semantic search service for AI agents, LLMs and RAG
applications. It is the `knowledge` member of the uv workspace
(`apps/knowledge`, import package `knowledge`).

The service is built as a sequence of features. Each page below documents
one feature: what it does, its endpoints, its settings, its data model and
how it is tested with pytest and behave.

## Features

1. [Foundation](00-foundation.md): application factory, internal
   sub-application, settings, logging and the health check.
2. [Data model](01-data-model.md): SQLAlchemy models, async session and the
   Alembic migration chain.
3. [OAuth2 authentication](02-authentication.md): bearer token validation,
   token exchange, scopes and tenant resolution.
4. [Collections](03-collections.md): collection API, ownership and access
   levels.

## Running the tests

Every command runs from the root of the workspace:

```bash
uv run --package knowledge --group dev pytest apps/knowledge
uv run --package knowledge --group dev behave apps/knowledge/features
```

Both suites are in-process: they use mocks and fakes and never need a
database, Redis or any external service.
