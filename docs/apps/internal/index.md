# internal

Internal admin dashboard for managing platform services: a FastAPI application
that renders server-side Jinja2 pages for operators. It authenticates users
against an OAuth2 / OIDC server and talks to the other platform services over
HTTP. The Python package is `internal`, a member of the uv workspace under
`apps/internal`.

The application was assembled feature by feature; each page below documents one
feature, in the order they were introduced.

## Features

1. [Application foundation](01-foundation.md)

## Running locally

```bash
uv sync --all-groups --package internal
uv run --package internal uvicorn internal.main:app --reload
```

Tests are run from the repository root:

```bash
uv run --package internal pytest apps/internal
uv run --package internal behave apps/internal/features
```

`pytest` covers the code with unit and route-handler tests. `behave` runs one
scenario file per feature, entirely in-process: the application is driven through
an ASGI transport, the database is a throw-away SQLite file and every outbound
service client is replaced by a mock. No PostgreSQL, Redis or network access is
needed.
