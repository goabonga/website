# analytics

Analytics tracking service for the platform, built feature by feature. Each
feature has its own implementation slice, pytest tests, a behave scenario
file and the page listed below.

- Workspace member: `apps/analytics` (distribution `analytics`, import package `analytics`)
- ASGI entry point: `analytics.main:app` (FastAPI)
- Data store: PostgreSQL through async SQLAlchemy and Alembic
- Cache: Redis (token introspection and scope caches)

## Features

- [Foundation](00-foundation.md): settings, logging, application and `/health`.
- [security.txt](01-security-txt.md): RFC 9116 vulnerability disclosure file.
- [Storage](02-storage.md): PostgreSQL models for sessions and events, Alembic revision `001`.
- [Visitor enrichment](03-enrichment.md): user agent parsing and optional GeoIP lookups.
- [Event collection](04-collection.md): `/collect` endpoints and session cookies.
- [Campaigns and pixels](05-pixels.md): email tracking pixels, Alembic revision `002`.
- [Campaign links](06-links.md): redirects with click tracking.
- [Authentication](07-auth.md): OAuth2/OIDC bearer tokens and scopes.
- [Traffic statistics](08-stats-traffic.md): overview, daily, countries, devices, browsers, referrers, pages, events.
- [IP statistics](09-stats-ips.md): most active IPs and per-IP detail.
- [Campaign statistics](10-stats-campaigns.md): campaign list and detail, pixel list.
- [Campaign management](11-campaign-api.md): creating and deleting campaigns and pixels.
