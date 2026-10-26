# Contact groups

Named sets of [contacts](09-contacts.md) used to target campaigns. Groups and
memberships are stored in the tables created by the contacts migration.

Groups are owned by a client (see [client identity](02-authentication.md)) and
their slugs are unique per client. A client only sees and changes its own
groups, and only its own contacts can be members of them. Administrators can
act on every client.

## Endpoints

All routes live under `/api/v1/contact-groups`.

| Endpoint | Method | Scope | Description |
| --- | --- | --- | --- |
| `/contact-groups` | GET | `mailler:read` | Paginated list of the client's groups with a search filter (`client_id` for administrators) |
| `/contact-groups` | POST | `mailler:write` | Create a group (`201`); administrators may pass `client_id` to create it for another client |
| `/contact-groups/{id}` | GET | `mailler:read` | Read by numeric id |
| `/contact-groups/by-slug/{slug}` | GET | `mailler:read` | Read by slug inside the caller's client (`client_id` for administrators) |
| `/contact-groups/{id}` | PUT | `mailler:write` | Update (partial body) |
| `/contact-groups/{id}` | DELETE | `mailler:write` | Delete (`204`); memberships are deleted with it |
| `/contact-groups/{id}/contacts` | GET | `mailler:read` | Contacts that belong to the group |
| `/contact-groups/{id}/available-contacts` | GET | `mailler:read` | Active contacts of the group's client that do not belong to the group |
| `/contact-groups/{id}/contacts` | POST | `mailler:write` | Add contacts (`{"contact_ids": [...]}`, 1 to 1000 ids) |
| `/contact-groups/{id}/contacts` | DELETE | `mailler:write` | Remove contacts (same body) |

## Behaviour

- A group has a `slug`, unique for its client (lowercase letters, digits and single
  hyphens), a `name`, an optional `description` and a member count derived
  from its active contacts.
- `is_dynamic` and `filter_criteria` can be stored to describe a filter-based
  group; they are plain data and the API does not evaluate them.
- Adding and removing members returns `{"added", "removed", "skipped"}`:
  contacts that are already members (or are not members, when removing) are
  skipped, and so are contacts that belong to another client than the group.
  An unknown group or a group of another client gives `404`; a duplicate slug
  inside the client `409`; an invalid slug `422`; naming another client
  without being an administrator `403`.
- The two member listings accept `page`, `page_size` and `search` (email and
  names) and return the same response as the contact list.

## How it is tested

- pytest: `tests/test_routes_contact_groups.py` and the group model cases in
  `tests/test_models.py`, plus routing cases in `tests/test_main.py`.
- behave: `features/contact_groups.feature` (listing and search, creation of
  static and dynamic groups, duplicate and invalid slugs, reads, update,
  delete, adding, listing, removing and re-adding members, scopes and
  authentication, and the isolation between clients: same slug for two
  clients, foreign groups hidden, memberships restricted to the client's own
  contacts, administrator creation) against the in-process SQLite database.
