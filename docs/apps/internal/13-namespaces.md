# Knowledge namespaces

Namespaces group the entries of the knowledge base (used for retrieval-augmented
generation) and decide who may read them. This is the first feature that owns its data: the pages
read and write the `knowledge_namespaces` table of the shared database directly, through async
SQLAlchemy. The entries that live in a namespace are managed by the knowledge base feature that follows;
the model of the entries is introduced here because it is defined in the same module.

## What it adds

| Module | Role |
| --- | --- |
| `internal/models/knowledge.py` | Knowledge base model for RAG - mirrors fastapi-api model. |
| `internal/routes/namespaces.py` | Knowledge Namespace CRUD routes. |

It also ships 3 Jinja2 template(s) under `internal/templates/` (packaged with the wheel).

## Endpoints

| Method | Path | Required scope | Description |
| --- | --- | --- | --- |
| GET | /namespaces | `namespaces:read` | List all namespaces with pagination and search. |
| GET | /namespaces/new | `namespaces:write` | Show form to create a new namespace. |
| POST | /namespaces/new | `namespaces:write` | Create a new namespace. |
| GET | /namespaces/{namespace_id} | `namespaces:read` | View namespace detail. |
| GET | /namespaces/{namespace_id}/edit | `namespaces:write` | Show form to edit a namespace. |
| POST | /namespaces/{namespace_id}/edit | `namespaces:write` | Update a namespace. |
| POST | /namespaces/bulk-delete | `namespaces:delete` | Delete multiple namespaces. |
| POST | /namespaces/{namespace_id}/delete | `namespaces:delete` | Delete a namespace. |

The list and detail pages request the whole `namespaces` resource plus `vpn:admin` and `billing:read` (navigation). `internal:*` grants all namespace scopes.

## Behaviour

- **List** (`/namespaces`): paginated, with a case-insensitive `search` over slug, name and description.
  Visiting the list creates the default `general` namespace (public, "General") when it is missing.
- **Create and edit** (`/namespaces/new`, `/namespaces/{id}/edit`): `slug` (lower-cased, unique - a
  duplicate redirects back with an error), `name`, `description`, `required_scopes` (comma-separated
  scopes a caller must hold to read the namespace) and `is_public`.
- **Detail** (`/namespaces/{id}`): the namespace and its entry count.
- **Delete** (single and bulk): the `general` namespace can never be deleted; a bulk delete skips it and reports
  how many namespaces were skipped. Entries of a deleted namespace keep existing with an empty
  namespace (`ON DELETE SET NULL`). The list sends the selection of a bulk delete as one comma-separated
  value, which the route splits. A form cannot be nested in another one, so the Delete button of an edit form carries its own `formaction` and confirmation: nested, the browser would drop the inner form and the button would save the page instead. A failed save redirects back to the form with an `error` message, which the form shows.

## Data model

The tables belong to the platform's chat backend (the models mirror its definitions); this
application reads and writes them but ships no migration. `required_scopes`, `metadata` and the
embedding use PostgreSQL array, JSONB and pgvector types.

**`KnowledgeNamespace`** maps the `knowledge_namespaces` table: `id`, `slug`, `name`, `description`, `required_scopes`, `is_public`, `metadata_`, `created_at`, `updated_at`.

**`KnowledgeEntry`** maps the `knowledge_base` table: `id`, `namespace_id`, `question`, `answer`, `embedding`, `metadata_`, `status`, `validation_details`, `created_at`, `updated_at`.

`KnowledgeEntryStatus` (`pending`, `validating`, `accepted`, `rejected`, `needs_review`) is the validation state of an entry; it becomes meaningful with the knowledge base feature.

## Tests

pytest:

- `tests/routes/test_namespaces.py`
- `tests/routes/test_namespaces_sidebar.py`

The tests cover each route handler with a mocked session (default namespace creation, duplicate slugs, bulk delete skipping the default) and the model imports. The bulk delete is also tested with the comma-separated selection the list page sends.

`tests/routes/test_namespaces_sidebar.py` opens every page of this feature through the application with its real templates (throw-away SQLite database, mocked service clients) and, for each scope combination, checks the sidebar: exactly the links the scopes permit, a single active link and the signed-in user.

Behave scenarios, run in-process with `uv run --package internal behave apps/internal/features` (`features/namespaces.feature`):

- List namespaces
- List namespaces with search filter
- List namespaces unauthenticated
- View new namespace form
- Create a namespace
- Create a namespace with duplicate slug
- View namespace detail
- View namespace detail not found
- View namespace edit form
- Update a namespace
- Delete a namespace
- Cannot delete the default general namespace
- Bulk delete namespaces
- Sidebar on the namespaces list
- Sidebar on the new namespace form
- Sidebar on the namespace detail
- Sidebar on the namespace edit form
- Sidebar gated links follow the scopes on the namespaces list

Scenarios run against the throw-away SQLite database: pgvector, array and JSONB columns are mapped to JSON for the run, so creation, search, uniqueness and deletion are checked end to end.

Browser scenarios, run in Chromium against the application served on a local socket (`features/browser/namespaces.feature`, `uv run --package internal --group dev behave apps/internal/features -t @browser`):

- The namespaces are listed
- The Namespaces link leads to the list
- A user without the namespace scope gets the access denied page
- A user who may only read cannot create a namespace
- An anonymous visitor comes back to the page asked for after the login
- Searching narrows the list
- The list is paginated and keeps the search
- A namespace is created from the form
- A slug already in use is reported on the form
- A restricted namespace asks for scopes
- A namespace is updated from its edit form
- Renaming the slug of a namespace to one already in use is reported
- A namespace that does not exist sends the user back to the list
- A namespace is deleted from its page after a confirmation
- A namespace is deleted from its edit form after a confirmation
- Dismissing the confirmation keeps the namespace
- The default namespace cannot be deleted
- Selected namespaces are deleted in bulk

The bulk selection deletes several namespaces at once and skips the default one, and the Delete button of the edit form deletes after a confirmation.
