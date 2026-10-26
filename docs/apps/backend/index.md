# backend

The main API service of the platform, a FastAPI application served at the
public API domain. The workspace member is `apps/backend` (distribution
`backend`, import package `backend`, ASGI application
`backend.main:app`).

The service is built feature by feature. Each page below documents one
feature: what it does, how it is configured, how it is tested.

## Features

1. [Application foundation](01-foundation.md): settings, logging, database
   base, FastAPI application and the `/health` probe.

## Running the tests

Run every command from the repository root.

```bash
# Unit tests
uv run --package backend --group dev pytest apps/backend

# Behave scenarios (in-process, no external services)
uv run --package backend --group dev behave apps/backend/features
```
