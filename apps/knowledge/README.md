# knowledge

Vector storage and semantic search SaaS for AI agents, LLMs and RAG
applications. It is a member of the `website` uv workspace.

## Features

- FastAPI application with a public API and a mounted internal
  sub-application, environment-driven settings, structured logging and a
  `/health` endpoint.
- PostgreSQL data model (SQLAlchemy 2.0 with pgvector) and Alembic
  migrations.
- OAuth2 bearer authentication with JWKS validation, token exchange and
  scope checks.
- Collections REST API (`/api/v1/collections`) with personal and
  organization ownership.
- Documents REST API with OpenAI embeddings stored in pgvector.
- Semantic similarity search (cosine, L2 and inner product) over
  collections.
- Collection sharing with collaborators and email invitations.
- Plan-based quotas and per-tenant API call tracking.
- Multi-tenant resolution from path prefix, subdomain or custom domain.
- Billing client and subscription webhook that keep organization plans in
  sync.
- Quota limits read from the billing plans, with a configured fail-safe.
- Transactional emails (MJML templates) sent through the mailler service.
- MCP executable releases imported from GitHub and served through a public
  download API.
- Celery worker and beat for email delivery and scheduled workspace deletion.
- Custom domains for Enterprise organizations, registered in the
  custom-domain service (status webhooks and reconciliation).
- Custom domain provisioning (DNS check, nginx virtual host, Let's Encrypt)
  for Enterprise organizations.
- Server-rendered signin, signup and account pages backed by the platform
  authentication service.
- Landing page, pricing, legal pages, dashboard and MCP download page.
- Collection and document management pages, with chunked and uploaded
  documents.

The documentation of every feature lives in `docs/apps/knowledge/`.

## Routes and scopes

HTTP routes served by the application and what each one requires. `public` routes need no bearer token or session. `session` routes need a signed-in user and redirect to the login page otherwise. A scope is checked on the access token issued by the `auth` application; the wildcards `*` and `<resource>:*` also match.

| Method | Path | Required scope / role / auth | Description |
| --- | --- | --- | --- |
| GET | `/health` | public | Health check endpoint |
| POST | `/webhooks/billing` | public; HMAC signature required (`BILLING_WEBHOOK_SECRET`) | Receive billing webhook events |
| POST | `/webhooks/custom-domain` | public; HMAC signature required (`CUSTOM_DOMAIN_WEBHOOK_SECRET`) | Receive a status notification of the custom-domain service |
| POST | `/webhooks/github/releases` | public; HMAC signature checked when `GITHUB_WEBHOOK_SECRET` is set | Receive GitHub release webhook events |
| GET | `/auth/login` | public | Redirect to OAuth2 authorization endpoint with PKCE |
| GET | `/auth/callback` | public | OAuth2 callback - exchange code for tokens |
| GET | `/auth/logout` | public | Log out by clearing cookies |
| POST | `/auth/refresh` | refresh token cookie | Refresh the access token |
| GET | `/auth/signup` | public | Display signup form |
| POST | `/auth/signup` | public | Process signup form submission |
| GET | `/auth/verify` | public | Display email verification form |
| POST | `/auth/verify` | public | Process email verification |
| POST | `/auth/verify/resend` | public | Resend verification email |
| GET | `/auth/signin` | public | Display signin form |
| POST | `/auth/signin` | public | Process signin form submission (ROPC grant) |
| GET | `/auth/create-workspace` | session | Display workspace creation form for users without a workspace |
| POST | `/auth/create-workspace` | session | Create a workspace for an authenticated user who has none |
| GET | `/auth/forgot-password` | public | Display forgot password form |
| POST | `/auth/forgot-password` | public | Process forgot password form submission |
| GET | `/auth/reset-password` | public | Display reset password form |
| POST | `/auth/reset-password` | public | Process reset password form submission |
| GET | `/auth/account` | session | Display account profile page |
| POST | `/auth/account` | session | Update account profile |
| GET | `/auth/account/security` | session | Display account security (MFA) page |
| POST | `/auth/account/security/setup` | session | Start TOTP setup |
| POST | `/auth/account/security/verify` | session | Verify TOTP code and enable MFA |
| POST | `/auth/account/security/disable` | session | Disable MFA |
| POST | `/auth/account/security/regenerate-codes` | session | Regenerate backup codes |
| GET | `/auth/account/password` | public | Redirect to security page (password is now part of security) |
| POST | `/auth/account/password` | session | Change password (redirects back to security page) |
| GET | `/` | public | Landing page - redirect to dashboard if logged in |
| GET | `/legal` | public | Legal notice page |
| GET | `/privacy` | public | Privacy policy page |
| GET | `/terms` | public | Terms of service page |
| GET | `/pricing` | public | Public pricing page with plans from billing API |
| GET | `/dashboard` | session | Main dashboard with stats and recent activity |
| GET | `/mcp` | public | Public MCP downloads page |
| GET | `/mcp/downloads` | public | Public MCP downloads page |
| GET | `/collections` | session | List all collections for the current tenant |
| GET | `/collections/new` | session | Show form to create a new collection |
| POST | `/collections/new` | session | Create a new collection |
| GET | `/collections/{collection_id}` | session | View a collection and its documents |
| GET | `/collections/{collection_id}/edit` | session | Show form to edit a collection |
| POST | `/collections/{collection_id}/edit` | session | Update a collection |
| POST | `/collections/{collection_id}/delete` | session | Delete a collection |
| POST | `/collections/{collection_id}/documents/delete` | session | Delete selected documents from a collection |
| GET | `/documents/{document_id}` | session | View a document's details |
| GET | `/documents/{collection_id}/new` | session | Show form to create a new document |
| POST | `/documents/{collection_id}/new` | session | Create a new document with embedding generation via OpenAI |
| GET | `/documents/{document_id}/edit` | session | Show form to edit a document |
| POST | `/documents/{document_id}/edit` | session | Update a document and regenerate embedding if content changed |
| POST | `/documents/{document_id}/delete` | session | Delete a document |
| POST | `/api/v1/collections` | bearer token; scope `collections:write` | Create a new collection |
| GET | `/api/v1/collections` | bearer token; scope `collections:read` | List all collections accessible to the authenticated user |
| GET | `/api/v1/collections/{collection_id}` | bearer token; scope `collections:read` | Get a collection by ID or slug |
| PATCH | `/api/v1/collections/{collection_id}` | bearer token; scope `collections:write` | Update a collection |
| DELETE | `/api/v1/collections/{collection_id}` | bearer token; scope `collections:write` | Delete a collection and all its documents |
| GET | `/api/v1/collections/{collection_id}/collaborators` | bearer token; scope `collections:read` | List all collaborators for a collection |
| POST | `/api/v1/collections/{collection_id}/collaborators` | bearer token; scope `collections:write` | Add a collaborator to a collection |
| PATCH | `/api/v1/collections/{collection_id}/collaborators/{user_id}` | bearer token; scope `collections:write` | Update a collaborator's permission level |
| DELETE | `/api/v1/collections/{collection_id}/collaborators/{user_id}` | bearer token; scope `collections:write` | Remove a collaborator from a collection |
| GET | `/api/v1/collections/{collection_id}/invitations` | bearer token; scope `collections:read` | List invitations for a collection |
| POST | `/api/v1/collections/{collection_id}/invitations` | bearer token; scope `collections:write` | Create an invitation to collaborate on a collection |
| DELETE | `/api/v1/collections/{collection_id}/invitations/{invitation_id}` | bearer token; scope `collections:write` | Revoke a pending invitation |
| POST | `/api/v1/collections/{collection_id}/invitations/{invitation_id}/resend` | bearer token; scope `collections:write` | Resend an invitation with a new token and expiry |
| GET | `/api/v1/collection-invites/{token}` | public | View an invitation by token |
| POST | `/api/v1/collection-invites/{token}/accept` | bearer token (any scope) | Accept an invitation to collaborate on a collection |
| POST | `/api/v1/collections/{collection_id}/documents` | bearer token; scope `documents:write` | Add documents to a collection |
| POST | `/api/v1/collections/{collection_id}/documents/single` | bearer token; scope `documents:write` | Add a single document to a collection |
| GET | `/api/v1/collections/{collection_id}/documents` | bearer token; scope `documents:read` | List documents in a collection |
| GET | `/api/v1/documents/{document_id}` | bearer token; scope `documents:read` | Get a document by ID |
| DELETE | `/api/v1/collections/{collection_id}/documents/{document_id}` | bearer token; scope `documents:write` | Delete a document |
| POST | `/api/v1/search` | bearer token; scope `collections:search` | Search across collections |
| POST | `/api/v1/search/collections/{collection_id}` | bearer token; scope `collections:search` | Search within a specific collection |
| GET | `/api/v1/mcp/releases` | public | List all published MCP releases |
| GET | `/api/v1/mcp/releases/latest` | public | Get the latest published MCP release |
| GET | `/api/v1/mcp/releases/{version}` | public | Get a specific MCP release by version |
| GET | `/api/v1/mcp/download/latest/{platform}` | public | Download the latest release for a platform |
| GET | `/api/v1/mcp/download/{version}/{platform}` | public | Download a specific release for a platform |

Swagger UI (`/docs`), ReDoc (`/redoc`) and `/openapi.json` are served only when `DOCS_ENABLED` is true.

The API routes also apply the per-collection access rules of the handlers (owner, collaborator permission, organization membership) on top of the scope.

### Scopes

The application defines no scope, it only checks the ones carried by the access tokens issued by the `auth` application, which grants them through its catalog of scopes and roles.

- `collections:write` - checked by 9 routes
- `collections:read` - checked by 4 routes
- `documents:write` - checked by 3 routes
- `documents:read` - checked by 2 routes
- `collections:search` - checked by 2 routes

## Local development

Run every command from the root of the workspace.

```bash
uv sync --package knowledge
uv run --package knowledge uvicorn knowledge.main:app --reload --port 8003
```

Start PostgreSQL (pgvector) and apply the migrations:

```bash
docker compose -f apps/knowledge/compose.yml up -d
uv run --package knowledge alembic -c apps/knowledge/alembic.ini upgrade head
```

Run a Celery worker and the beat scheduler:

```bash
uv run --package knowledge celery -A knowledge.celery:celery_app worker -Q knowledge
uv run --package knowledge celery -A knowledge.celery:celery_app beat
```

Settings are read from environment variables or a `.env` file in the working
directory.

## Tests

The suites use mocks and need no running database or Redis:

```bash
uv run --package knowledge --group dev pytest apps/knowledge
uv run --package knowledge --group dev behave apps/knowledge/features
```

The behave scenarios tagged `@browser` drive the web pages in a real Chromium; they are
skipped when the browser is not installed or when `E2E_SKIP_BROWSER=1`, and
`behave ... -t ~@browser` leaves them out.
