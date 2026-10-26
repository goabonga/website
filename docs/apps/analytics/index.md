# analytics

Analytics tracking service for the platform, built feature by feature. Each
feature has its own implementation slice, pytest tests, a behave scenario
file and the page listed below.

- Workspace member: `apps/analytics` (distribution `analytics`, import package `analytics`)
- ASGI entry point: `analytics.main:app` (FastAPI)
- Data store: PostgreSQL through async SQLAlchemy and Alembic

## Features

- [Foundation](00-foundation.md): settings, logging, application and `/health`.
- [security.txt](01-security-txt.md): RFC 9116 vulnerability disclosure file.
- [Storage](02-storage.md): PostgreSQL models for sessions and events, Alembic revision `001`.
- [Visitor enrichment](03-enrichment.md): user agent parsing and optional GeoIP lookups.
