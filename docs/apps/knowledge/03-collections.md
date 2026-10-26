# Collections

A collection is a named group of documents. It is the unit of ownership,
sharing and search: documents always live inside one collection. This feature
adds the collection REST API under `/api/v1/collections`.

## Ownership

Collections have a polymorphic owner (`owner_type` + `owner_id`):

- `user`: a personal collection, owned by the authenticated user;
- `organization`: a collection owned by an organization the user belongs to.
  The legacy `tenant_id` column is also set to the organization id.

Slugs are unique per owner, not globally. A personal collection has no
organization, so `tenant_id` is `null` in its response.

## Endpoints

All endpoints require a bearer token (see [OAuth2
authentication](02-authentication.md)) and are tagged `Collections` in the
public OpenAPI document.

| Method | Path | Scope | Description |
| --- | --- | --- | --- |
| `POST` | `/api/v1/collections` | `collections:write` | Create a collection. Personal by default; with `?organization_id=<uuid>` the collection is created in that organization. |
| `GET` | `/api/v1/collections` | `collections:read` | List accessible collections (`offset`, `limit`, `owner_type`, `organization_id`, `include_shared`). |
| `GET` | `/api/v1/collections/{id_or_slug}` | `collections:read` | Get a collection by UUID or by slug. |
| `PATCH` | `/api/v1/collections/{id}` | `collections:write` | Update `name`, `description` or `metadata_schema`. |
| `DELETE` | `/api/v1/collections/{id}` | `collections:write` | Delete a collection and all its documents (`204`). |

Creating a collection returns `201`, a duplicate slug for the same owner
returns `409`, and a payload that does not validate returns `422`. A
collection that does not exist, or that the caller cannot see, returns `404`.

### Payloads

`CollectionCreate`: `name` (1-255 characters), `slug` (1-100 characters,
lowercase letters, digits and dashes), optional `description` (up to 1000
characters), `embedding_model` (default `text-embedding-3-small`),
`dimension` (1-4096, default `1536`) and an optional `metadata_schema`
object.

`CollectionResponse`: `id`, `tenant_id`, `name`, `slug`, `description`,
`embedding_model`, `dimension`, `metadata_schema`, `document_count`,
`created_at`, `updated_at`.

### Listing rules

Without filters the list contains the personal collections of the caller, the
collections the caller collaborates on (unless `include_shared=false`) and
the collections of every organization the caller is a member of.
`owner_type=user` restricts the list to personal collections;
`organization_id` restricts it to one organization and answers `403` when the
caller is not a member.

## Access levels

`CollectionAccessService` resolves the effective `AccessLevel` of a user on a
collection; the highest level wins:

| Level | Granted by |
| --- | --- |
| `owner` | Owning a personal collection, or being the owner of the organization. |
| `admin` | Organization admin, or `admin` collaborator. |
| `write` | Organization member (members get write access to organization collections), or `write` collaborator. |
| `read` | `read` collaborator. |
| `none` | Anything else. |

Updating requires `write`, deleting requires `owner`, and creating a
collection in an organization requires being an organization owner or admin,
or a member when the organization setting `allow_member_create_collections`
is enabled (the default). Collaborator permissions are managed by the
collaboration feature.

## Tests

pytest:

- `test_collections.py`: the five endpoints with mocked session and
  authentication: scopes, conflicts, filters, organization collections,
  access checks.
- `unit/test_collection_service.py`: the polymorphic query methods of
  `CollectionService` and the legacy tenant-based methods.
- `unit/test_collection_access.py`: access-level resolution, `can_*` helpers
  and organization creation rights.
- `unit/test_schemas.py`: payload validation and the response for personal
  and organization collections.

behave (`features/collections.feature`), with an in-memory stand-in for the
collection service:

- Create a personal collection
- A duplicate slug is rejected
- An invalid slug is rejected
- List my collections
- Get a collection by slug
- An unknown collection is not found
- Update a collection
- Delete a collection
- Reading requires the read scope
- Writing requires the write scope
