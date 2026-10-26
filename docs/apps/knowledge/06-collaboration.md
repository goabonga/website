# Collaborators and invitations

Collaboration lets the owner of a collection share it with other users, either
directly by user id or through an email invitation that the invitee accepts.
It builds on the [collections](03-collections.md) access levels.

## Permissions

A collaborator holds one `CollaboratorPermission` on one collection:

| Permission | Allows |
| --- | --- |
| `read` | Reading the collection. |
| `write` | Reading and writing. |
| `admin` | Reading, writing, managing collaborators and invitations. |

Only owners and `admin` collaborators (or organization admins) can manage
collaborators and invitations; every collaboration route first loads the
collection through `CollectionService.get_accessible`, so a user who cannot
see the collection gets `404`, and a user who sees it without the right level
gets `403`.

## Collaborator endpoints

Prefix `/api/v1/collections/{collection_id}/collaborators`, tag
`Collaborators`.

| Method | Path | Scope | Description |
| --- | --- | --- | --- |
| `GET` | `` | `collections:read` | List collaborators (`offset`, `limit`). Needs read access. |
| `POST` | `` | `collections:write` | Add `{user_id, permission}` (default `read`). `201`; `400` when adding yourself; `409` when already a collaborator. |
| `PATCH` | `/{user_id}` | `collections:write` | Change the permission. `404` when the user is not a collaborator. |
| `DELETE` | `/{user_id}` | `collections:write` | Remove a collaborator (`204`). A collaborator can always remove themselves. |

## Invitation endpoints

Collection-scoped routes use the prefix
`/api/v1/collections/{collection_id}/invitations`; the public routes use
`/api/v1/collection-invites`. Both are tagged `Collection Invitations`.

| Method | Path | Scope | Description |
| --- | --- | --- | --- |
| `GET` | `/api/v1/collections/{id}/invitations` | `collections:read` | List invitations (`status_filter`, `offset`, `limit`). Needs admin access. |
| `POST` | `/api/v1/collections/{id}/invitations` | `collections:write` | Invite `{email, permission}`. Returns `201` with the token to share. `409` when a pending invitation already exists for the address; the email must be valid (`422`) and is stored lowercased. |
| `DELETE` | `/api/v1/collections/{id}/invitations/{invitation_id}` | `collections:write` | Revoke a pending invitation (`204`); `400` when it was already processed. |
| `POST` | `/api/v1/collections/{id}/invitations/{invitation_id}/resend` | `collections:write` | Issue a new token and a new expiry for a pending invitation. |
| `GET` | `/api/v1/collection-invites/{token}` | none | Public view: collection name, permission, `is_valid`, `is_expired`. |
| `POST` | `/api/v1/collection-invites/{token}/accept` | any authenticated user | Accept the invitation and become a collaborator. |

Invitations are valid for 7 days. Tokens are 32 random bytes encoded
URL-safe. Accepting an expired invitation marks it `expired` and answers
`400 Invitation has expired`; accepting a revoked or already accepted one
answers `400 Invitation is <status>`. If the accepting user already is a
collaborator the invitation is accepted without creating a duplicate. The
service does not send any email: the token is returned to the caller, who is
responsible for delivering it. Housekeeping helpers (`expire_old_invitations`,
`delete_old_invitations`) exist on `CollectionInvitationService`.

## Data model

Collaborators are stored in `collection_collaborators` (unique per collection
and user) and invitations in `collection_invitations` (unique token, status
`pending`, `accepted`, `expired` or `revoked`); both are described in the
[data model](01-data-model.md). The email validation of the payloads needs the
`email-validator` package, installed through `pydantic[email]`.

## Tests

pytest:

- `test_collaborator_routes.py` and `test_collection_invitation_routes.py`:
  every route with mocked services and authentication: scopes, access
  checks, conflicts and error mapping.
- `unit/test_collaborator_service.py`: list, get, add, update, remove, count
  and bulk removal.
- `unit/test_collection_invitation_service.py`: creation, lookups, listing,
  acceptance rules, revocation, resend, expiry and cleanup.

behave (`features/collaboration.feature`): the real services run over an
in-memory store (only the read queries are replaced), with real models and
route validation.

- Add a collaborator
- A user cannot add themselves as collaborator
- A collaborator cannot be added twice
- List the collaborators of a collection
- Change the permission of a collaborator
- Remove a collaborator
- A read-only collaborator cannot add collaborators
- A collaborator can leave a collection
- Collaborators of an unknown collection are not found
- Create an invitation
- A pending invitation cannot be duplicated
- An invalid email is rejected
- List the invitations of a collection
- View an invitation without authentication
- Accept an invitation
- A revoked invitation cannot be accepted
- Resending an invitation issues a new token
- An unknown invitation token is not found
