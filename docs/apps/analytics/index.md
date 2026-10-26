# analytics

Analytics tracking service for the platform, built feature by feature. Each
feature has its own implementation slice, pytest tests, a behave scenario
file and the page listed below.

- Workspace member: `apps/analytics` (distribution `analytics`, import package `analytics`)
- ASGI entry point: `analytics.main:app` (FastAPI)

## Features

- [Foundation](00-foundation.md): settings, logging, application and `/health`.
