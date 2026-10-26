# Contact groups

Contact groups are named lists of contacts used to target e-mail campaigns. This feature adds
their administration pages on top of the contact management feature; as there, the data
lives in the mailler service and is read and written through the mailler client.

## What it adds

| Module | Role |
| --- | --- |
| `internal/routes/contact_groups.py` | Contact Groups CRUD routes. |

It also ships 4 Jinja2 template(s) under `internal/templates/` (packaged with the wheel).

## Endpoints

| Method | Path | Required scope | Description |
| --- | --- | --- | --- |
| GET | /contact-groups | `contacts:read` | List all contact groups with pagination. |
| GET | /contact-groups/new | `contacts:write` | Show form to create a new contact group. |
| POST | /contact-groups/new | `contacts:write` | Create a new contact group. |
| GET | /contact-groups/{group_id} | `contacts:read` | View contact group detail with member list. |
| GET | /contact-groups/{group_id}/edit | `contacts:write` | Show form to edit a contact group. |
| POST | /contact-groups/{group_id}/edit | `contacts:write` | Update a contact group. |
| GET | /contact-groups/{group_id}/add-contacts | `contacts:write` | Show form to add contacts to a group. |
| POST | /contact-groups/{group_id}/add-contacts | `contacts:write` | Add contacts to a group. |
| POST | /contact-groups/{group_id}/remove-contacts | `contacts:write` | Remove contacts from a group. |
| POST | /contact-groups/bulk-delete | `contacts:delete` | Delete multiple contact groups. |
| POST | /contact-groups/{group_id}/delete | `contacts:delete` | Delete a contact group. |

Groups share the `contacts` scopes: `contacts:read` to look, `contacts:write` to change membership, `contacts:delete` to remove groups.

## Pages

- **List** (`/contact-groups`): paginated list of groups.
- **Create and edit** (`/contact-groups/new`, `/contact-groups/{id}/edit`): `name` (required), an
  optional `slug` and a description.
- **Detail** (`/contact-groups/{id}`): the group with its member list; members can be removed
  (`POST .../remove-contacts`).
- **Add contacts** (`/contact-groups/{id}/add-contacts`): shows the contacts that are not yet
  in the group and adds the selected ones.
- **Delete** (`POST .../delete`, `POST /contact-groups/bulk-delete`): needs `contacts:delete`. A form cannot be nested in another one, so the Delete button of an edit form carries its own `formaction` and confirmation: nested, the browser would drop the inner form and the button would save the page instead. A failed save redirects back to the form with an `error` message, which the form shows.

## Tests

pytest:

- `tests/routes/test_contact_groups.py`
- `tests/routes/test_contact_groups_sidebar.py`

The tests cover each route handler (pagination, membership changes, validation and error redirects). The forms and the add-contacts page are tested for the error message they show.

`tests/routes/test_contact_groups_sidebar.py` opens every page of this feature through the application with its real templates (throw-away SQLite database, mocked service clients) and, for each scope combination, checks the sidebar: exactly the links the scopes permit, a single active link and the signed-in user.

Behave scenarios, run in-process with `uv run --package internal behave apps/internal/features` (`features/contact_groups.feature`):

- View contact groups list
- View contact groups list unauthenticated
- View contact groups list with search
- View new group form
- Create a contact group successfully
- Create a contact group failure
- View group detail
- View group detail not found
- View group edit form
- View group edit form not found
- Update a contact group successfully
- Update a contact group failure
- View add contacts form
- Add contacts to a group successfully
- Add contacts with none selected
- Remove contacts from a group
- Remove contacts with none selected
- Delete a contact group successfully
- Delete a contact group not found
- Bulk delete contact groups
- Sidebar on the contact groups list
- Sidebar on the new contact group form
- Sidebar on the contact group detail
- Sidebar on the contact group edit form
- Sidebar on the add contacts form
- Sidebar gated links follow the scopes on the contact groups list

The mailler client is replaced by an `AsyncMock`; scenarios cover listing, create and edit, membership changes, deletion and unauthorized access.

Browser scenarios, run in Chromium against the application served on a local socket (`features/browser/contact_groups.feature`, `uv run --package internal --group dev behave apps/internal/features -t @browser`):

- The groups are listed
- The Contact Groups link leads to the list
- A user without the contacts scope gets the access denied page
- An anonymous visitor comes back to the page asked for after the login
- Searching the groups keeps the search in the address
- A group is created from the form
- A group the mailler service refuses is reported on the form
- The slug is derived from the name while typing
- A group is updated from its edit form
- A group the mailler service cannot update is reported on the form
- A group that does not exist sends the user back to the list
- The detail of a group lists its members
- The members are added to a group from the list of the other contacts
- The error of a refused addition is shown on the page
- A member is removed from a group
- A group is deleted from its page after a confirmation
- A group is deleted from its edit form after a confirmation
- Selected groups are deleted in bulk

The slug is derived from the name in the browser, members are added and removed from their pages, and the Delete button of the edit form deletes the group.
