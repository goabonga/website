# Contacts

The recipients database: contacts with a lifecycle status, custom fields,
bulk import and unsubscribe. Contact groups, which reuse the same tables,
are covered by the next feature.

Contacts are owned by a client (see [client identity](02-authentication.md)):
a client only lists, reads, edits, unsubscribes and deletes its own contacts,
and the same address can be a contact of several clients independently.
Administrators can act on every client.

## Endpoints

All routes live under `/api/v1/contacts`.

| Endpoint | Method | Scope | Description |
| --- | --- | --- | --- |
| `/contacts` | GET | `mailler:read` | Paginated list of the client's contacts (`page`, `page_size`, `status`, `search` on email and name, `group_id`; `client_id` for administrators) |
| `/contacts` | POST | `mailler:write` | Create a contact (`201`); administrators may pass `client_id` to create it for another client |
| `/contacts/bulk` | POST | `mailler:write` | Create up to 1000 contacts at once (`201`); same `client_id` rule |
| `/contacts/{id}` | GET | `mailler:read` | Read by UUID |
| `/contacts/by-email/{email}` | GET | `mailler:read` | Read by email address inside the caller's client (`client_id` for administrators) |
| `/contacts/{id}` | PUT | `mailler:write` | Update (partial body) |
| `/contacts/{id}` | DELETE | `mailler:write` | Delete (`204`) |
| `/contacts/{id}/unsubscribe` | POST | `mailler:write` | Set the status to `unsubscribed` |

## Behaviour

- A contact has an `email` (validated) that is unique inside its client, optional `first_name`,
  `last_name`, `source` and free-form `custom_fields`, and a `status`:
  `active` (default), `unsubscribed`, `bounced` or `complained`. The
  `full_name` is derived from the two names.
- A duplicate email inside the same client gives `409`, an invalid email
  `422`, an unknown contact or a contact of another client `404`, and naming
  another client without being an administrator `403`.
- Bulk creation reports `created`, `skipped` (already existing emails, when
  `skip_existing` is true, which is the default; otherwise they are counted
  as `failed`) and `failed`, with the error messages.
- When a contact whose status is `bounced` or `complained` is set back to
  `active`, and the Brevo provider is configured, the address is also
  unblocked on Brevo's side (a failure is logged and does not fail the
  update).
- `group_id` restricts the list to the members of a contact group.

## Data model and migration

Alembic revision `003` creates three tables: `contacts` (required `client_id`,
unique `(client_id, email)`, status, source, JSONB `custom_fields`),
`contact_groups` (required `client_id`, unique `(client_id, slug)`) and
`contact_group_members` (the association, with a unique pair and cascading
deletes). The migration checks whether each table or index already exists
before creating it, so it also works on a database that was prepared by
hand; this also means it cannot be rendered with `alembic --sql` (offline
mode).

## How it is tested

- pytest: `tests/test_routes_contacts.py` and the contact model cases in
  `tests/test_models.py`, plus routing cases in `tests/test_main.py`.
- behave: `features/contacts.feature` (listing, pagination, search and
  status filters, creation, duplicates and validation, bulk creation with
  and without skipping, reads by id and email, update, status change,
  delete, unsubscribe, scopes and authentication, and the isolation between
  clients: same address for two clients, foreign contacts hidden, bulk
  creation per client, administrator view) against the in-process SQLite
  database.
