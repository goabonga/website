# Contact management

Management of the mailing contacts: browse, search, create, edit, unsubscribe and delete
contacts, import them from CSV and export them. The contacts themselves are stored by the
mailler service; every operation goes through the mailler client introduced with the
mailler feature. This feature also adds the SQLAlchemy mapping of the contact tables that the
campaign models (a later feature) build on.

## What it adds

| Module | Role |
| --- | --- |
| `internal/models/contact.py` | Contact and ContactGroup models for email campaigns. |
| `internal/routes/contacts.py` | Contacts CRUD routes with CSV import/export. |

It also ships 4 Jinja2 template(s) under `internal/templates/` (packaged with the wheel).

## Endpoints

| Method | Path | Required scope | Description |
| --- | --- | --- | --- |
| GET | /contacts | `contacts:read` | List all contacts with pagination, search, and filtering. |
| GET | /contacts/new | `contacts:write` | Show form to create a new contact. |
| POST | /contacts/new | `contacts:write` | Create a new contact. |
| GET | /contacts/import | `contacts:write` | Show CSV import form. |
| POST | /contacts/import | `contacts:write` | Import contacts from CSV file. |
| GET | /contacts/export | `contacts:read` | Export contacts to CSV file. |
| GET | /contacts/{contact_id} | `contacts:read` | View contact detail. |
| GET | /contacts/{contact_id}/edit | `contacts:write` | Show form to edit a contact. |
| POST | /contacts/{contact_id}/edit | `contacts:write` | Update a contact. |
| POST | /contacts/{contact_id}/unsubscribe | `contacts:write` | Mark a contact as unsubscribed. |
| POST | /contacts/{contact_id}/delete | `contacts:delete` | Delete a contact. |
| POST | /contacts/bulk-delete | `contacts:delete` | Delete multiple contacts. |
| POST | /contacts/bulk-add-to-group | `contacts:write` | Add multiple contacts to a group. |

The list and detail pages request the whole `contacts` resource plus `vpn:admin` and `billing:read` (navigation); write actions need `contacts:write`.

## Pages

- **List** (`/contacts`): 50 per page, with `search`, `status` (`active`, `unsubscribed`,
  `bounced`, `complained`) and `group` filters. The group filter is fed by the first 100
  contact groups.
- **Create, edit, detail** (`/contacts/new`, `/contacts/{id}`, `/contacts/{id}/edit`): email
  (fixed once created), first and last name, status, source and the groups the contact belongs to.
- **Unsubscribe** (`POST /contacts/{id}/unsubscribe`): marks a contact as unsubscribed.
- **Delete** (`POST /contacts/{id}/delete`, `POST /contacts/bulk-delete`): needs `contacts:delete`. A form cannot be nested in another one, so the Delete button of an edit form carries its own `formaction` and confirmation: nested, the browser would drop the inner form and the button would save the page instead. A failed save redirects back to the form with an `error` message, which the form shows. A `group`
  filter that is not a number is ignored.
- **Bulk add to group** (`POST /contacts/bulk-add-to-group`): adds the selected contacts to a
  contact group (the group pages themselves arrive with the next feature).
- **CSV import** (`/contacts/import`): the file must end in `.csv`; it is decoded as UTF-8
  (a BOM is accepted); the columns `email` (required, lower-cased), `first_name` and `last_name` are
  read, and the `source` form field (default `csv_import`) is applied to every row. Existing contacts are skipped
  unless "update existing" is ticked. The redirect message reports created, skipped and failed counts.
- **CSV export** (`/contacts/export`): downloads `email,first_name,last_name,status,source`,
  optionally restricted to a group.

## Data model

These models describe the tables the mailler service owns in the shared database. The route
handlers of this feature do not use them (they call the mailler API); they exist so that
the campaign models can reference contacts and groups.

**`Contact`** maps the `contacts` table: `id`, `email`, `first_name`, `last_name`, `status`, `source`, `custom_fields`, `created_at`, `updated_at`.

**`ContactGroup`** maps the `contact_groups` table: `id`, `slug`, `name`, `description`, `is_dynamic`, `filter_criteria`, `created_at`, `updated_at`.

**`ContactGroupMember`** maps the `contact_group_members` table: `id`, `contact_id`, `group_id`, `created_at`.

`ContactStatus` is a string enum with `active`, `unsubscribed`, `bounced` and `complained`. No migrations are shipped.

## Tests

pytest:

- `tests/routes/test_contacts.py`
- `tests/routes/test_contacts_sidebar.py`

The tests cover each route handler (filters, CSV import edge cases, export, bulk actions, error redirects) and the model properties and enums. The forms are tested for the error message of a failed save, and the list and the export for a group filter that is not a number.

`tests/routes/test_contacts_sidebar.py` opens every page of this feature through the application with its real templates (throw-away SQLite database, mocked service clients) and, for each scope combination, checks the sidebar: exactly the links the scopes permit, a single active link and the signed-in user.

Behave scenarios, run in-process with `uv run --package internal behave apps/internal/features` (`features/contacts.feature`):

- View contacts list
- View contacts list unauthenticated
- View contacts list with search filter
- View contacts list with status filter
- View new contact form
- Create a new contact successfully
- Create a new contact failure
- View import form
- Export contacts as CSV
- View contact detail
- View contact detail not found
- View contact edit form
- View contact edit form not found
- Update a contact successfully
- Update a contact failure
- Unsubscribe a contact successfully
- Unsubscribe a contact failure
- Delete a contact successfully
- Delete a contact failure
- Bulk delete contacts
- Bulk delete with no contacts selected
- Bulk add contacts to group
- Sidebar on the contacts list
- Sidebar on the new contact form
- Sidebar on the contact import form
- Sidebar on the contact detail
- Sidebar on the contact edit form
- Sidebar gated links follow the scopes on the contacts list

The mailler client is replaced by an `AsyncMock`; scenarios cover listing and filtering, create and edit, import and export, deletion and unauthorized access.

Browser scenarios, run in Chromium against the application served on a local socket (`features/browser/contacts.feature`, `uv run --package internal --group dev behave apps/internal/features -t @browser`):

- The contacts are listed
- The Contacts link leads to the list
- A user without the contacts scope gets the access denied page
- A user who may only read cannot create or import
- An anonymous visitor comes back to the filtered list after the login
- Searching narrows the list
- Filtering by status and group
- The list is paginated and keeps the search
- A group that is not a number in the address is ignored
- A contact is created and put in a group
- The form stops an address that is not an email
- A contact the mailler service refuses is reported on the form
- The list leads to the detail of a contact
- A contact that does not exist sends the user back to the list
- A contact is updated from its edit form
- A contact the mailler service cannot update is reported
- A contact is unsubscribed
- A contact is deleted from its page after a confirmation
- A contact is deleted from its edit form after a confirmation
- Dismissing the confirmation keeps the contact
- A contact the mailler service cannot delete is reported
- The bulk actions appear when contacts are selected
- Selected contacts are deleted in bulk
- Selected contacts are added to a group in bulk
- Adding to a group needs a group
- Contacts are imported from a CSV file
- A file that is not a CSV is refused
- A CSV without any valid contact is refused
- The contacts are exported as a CSV file

The CSV import uploads a file with the browser, the export is downloaded and read, the bulk actions appear when contacts are selected, and the Delete button of the edit form deletes the contact after a confirmation instead of saving the form.
