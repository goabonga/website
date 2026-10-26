# Data model

The data model defines every table of the service as SQLAlchemy 2.0
declarative models, the async session dependency used by the routes and the
Alembic migrations that create and evolve the schema in PostgreSQL with the
`pgvector` extension.

## Session management

`knowledge.database` creates the async engine from `DATABASE_URL`
(`asyncpg` driver, pool of 10 connections plus 20 overflow, `pool_pre_ping`)
and exposes:

- `async_session_factory`: `async_sessionmaker` with `expire_on_commit=False`;
- `get_db()`: FastAPI dependency that yields a session, commits when the
  request succeeds and rolls back before re-raising when it fails.

`knowledge.models.base.Base` is kept in its own module so that Alembic can
import the metadata without creating the engine.

## Tables

| Table | Model | Purpose |
| --- | --- | --- |
| `tenants` | `Organization` (alias `Tenant`) | Shared workspace (Enterprise plan): name, unique slug, plan, JSON settings, active flag and the custom domain fields. |
| `tenant_members` | `OrganizationMember` (alias `TenantMember`) | Membership of a user in an organization with a role (`owner`, `admin`, `member`), optional display name and email. Unique per `(tenant_id, user_id)`. |
| `invitations` | `OrganizationInvitation` (alias `Invitation`) | Email invitation to join an organization: role, unique token, status, expiry. |
| `collections` | `Collection` | Group of documents with polymorphic ownership: `owner_type` (`user` or `organization`) and `owner_id`. Unique per `(owner_type, owner_id, slug)`. `tenant_id` stays as a nullable legacy reference to the organization. |
| `documents` | `Document` | Knowledge entry: content, 1536-dimension `embedding` (pgvector, HNSW cosine index), JSON `metadata`, source, content hash, content and embedding sizes. |
| `collection_collaborators` | `CollectionCollaborator` | Per-user access to a collection with a permission (`read`, `write`, `admin`). Unique per `(collection_id, user_id)`. |
| `collection_invitations` | `CollectionInvitation` | Email invitation to collaborate on a collection: permission, unique token, status, expiry. |
| `usage_records` | `UsageRecord` | Usage counters per tenant, metric and period. |
| `user_plans` | `UserPlan` | Plan and settings of a personal account (primary key `user_id`). |
| `workspace_deletion_requests` | `WorkspaceDeletionRequest` | Confirmation, scheduling and reminder state of an organization deletion. |
| `mcp_releases` | `McpRelease` | Published release of the Knowledge MCP executable (unique GitHub release id). |
| `mcp_release_assets` | `McpReleaseAsset` | One downloadable binary per platform of a release, with checksum and download counter. |

The table names `tenants` and `tenant_members` are historical: the code
speaks of *organizations* while the schema keeps the original names, and the
`Tenant*` aliases remain importable from `knowledge.models`.

Enumerations live in `knowledge.models.enums`: `PlanType` (`free`,
`starter`, `pro`, `enterprise`), `OwnerType`, `CollaboratorPermission`,
`OrganizationMemberRole`, `InvitationStatus`, `CustomDomainStatus`,
`ReleaseStatus` and `Platform`. `DeletionRequestStatus` is defined next to
its model.

The models also carry the small pieces of domain logic that do not need a
session: ownership checks on collections, permission checks on members and
collaborators, token generation, expiry computation and the
accept / revoke / expire transitions of invitations and deletion requests.

## Migrations

Migrations live in `apps/knowledge/alembic/versions` and form a single
linear chain:

| Revision | Content |
| --- | --- |
| `001_initial` | `pgvector` extension, `tenants`, `collections`, `documents` (with the HNSW index) and `usage_records`. |
| `002_multi_tenant_web` | `tenant_members`, `invitations` and the document size columns. |
| `003_github_ownership` | Polymorphic collection ownership, `user_plans`, `collection_collaborators` and `collection_invitations`. |
| `004_workspace_deletion_requests` | `workspace_deletion_requests`. |
| `005_member_display_info` | `display_name` and `email` on `tenant_members`. |
| `006_mcp_releases` | `mcp_releases` and `mcp_release_assets`. |
| `007_workspace_deletion_scheduled` | `scheduled` deletion status, scheduling and reminder columns. |
| `008_add_custom_domain_fields` | Custom domain columns and status enum on `tenants`. |

Revisions `003` to `007` check whether each object already
exists before creating it, so they can be replayed on a database that was
partly created by an earlier version.

`alembic/env.py` reads `DATABASE_URL`, converts the async URL to a
synchronous one (`psycopg2`) and supports online and offline modes (offline
SQL generation only works up to `002_multi_tenant_web`, because later
revisions inspect the live database). The
configuration file is `apps/knowledge/alembic.ini`; run it from the root of
the workspace:

```bash
docker compose -f apps/knowledge/compose.yml up -d
uv run --package knowledge alembic -c apps/knowledge/alembic.ini upgrade head
```

`compose.yml` starts a `pgvector/pgvector:pg17` container (database
`knowledge_test`, user and password `knowledge`, published on port `5440`),
which matches the default `DATABASE_URL`.

## Settings

| Variable | Default | Description |
| --- | --- | --- |
| `DATABASE_URL` | `postgresql+asyncpg://knowledge:knowledge@localhost:5440/knowledge_test` | SQLAlchemy async URL of the PostgreSQL database. A Unix-socket URL such as `postgresql+asyncpg://knowledge@/knowledge?host=/var/run/postgresql` is also supported. |

## Tests

pytest:

- `unit/test_models.py`: ownership, permission and lifecycle logic of the
  collection, collaborator, invitation, organization, member and deletion
  request models.
- `unit/test_database.py`: `get_db` commits on success and rolls back on
  error.
- `unit/test_migrations.py`: single base and single head, linear and ordered
  chain, downgrades present, and the metadata matches the expected tables.

behave (`features/data_model.feature`):

- The migration history has a single head
- The first migrations render as SQL without a database
- The declared models cover the whole schema
- A collection owned by a user is personal
- A collection owned by an organization is shared
- Only enterprise organizations can use custom domains
