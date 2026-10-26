# Collection and document pages

Signed-in users manage the collections and documents of their active
workspace from the browser. The pages are served by the internal
sub-application (tag `Web`), mounted under `/collections` and `/documents`, and
rendered with Jinja2. Every route depends on `get_web_auth_context` (see [Web
authentication](14-web-authentication.md)): visitors without a session are
redirected to the login page, and users without an active workspace are sent
back to `/collections`.

The pages work on the collections that belong to the active workspace through
the legacy workspace link (`collections.tenant_id`); a collection created here
is an organization-owned collection of that workspace.

## Collections

| Route | Behavior |
| --- | --- |
| `GET /collections` | Paginated list (20 per page, most recently updated first) with the number of documents of each collection. |
| `GET`/`POST /collections/new` | Creation form. The slug is derived from the name (lowercase, non-alphanumeric characters replaced by dashes, at most 100 characters). The [plan quota](07-quotas.md) is enforced first: when the limit is reached the form is shown again with the error. A name whose slug is already used by a collection of the workspace is refused the same way (status 400). |
| `GET /collections/{id}` | Collection page with its paginated documents (20 per page, newest first). |
| `GET`/`POST /collections/{id}/edit` | Rename and change the description. |
| `POST /collections/{id}/delete` | Delete the collection and its documents. |
| `POST /collections/{id}/documents/delete` | Delete the selected documents (`document_ids`). |

A collection that does not exist or belongs to another workspace redirects to
the list.

## Documents

| Route | Behavior |
| --- | --- |
| `GET /documents/{id}` | Document page with its collection as breadcrumb and its size. |
| `GET`/`POST /documents/{collection_id}/new` | Creation form: pasted text and/or an uploaded file (decoded as UTF-8, the file name becomes the `source_ref` and the source type defaults to `file`), optional source type and reference. |
| `GET`/`POST /documents/{id}/edit` | Edit the content and the source. The embedding is regenerated only when the content changed; increasing the stored size is checked against the storage quota. |
| `POST /documents/{id}/delete` | Delete the document and go back to its collection. |

Creating a document goes through `DocumentService` (hash, sizes and OpenAI
embedding, see [Documents](04-documents.md)), after checking the document and
storage quotas before every chunk. Content that is empty after trimming is
refused with `400`; any failure while embedding rolls back and redirects to the
form with the error message.

### Chunking

When "enable chunking" is selected, the text is split into several documents
before embedding:

| `chunk_mode` | Result |
| --- | --- |
| `markdown_sections` | One document per Markdown heading section (text without heading stays whole). |
| `split_5` / `split_10` | The text is cut into 5 or 10 balanced pieces by words. |

Each document records `chunked`, `chunk_mode` and `chunk_count` in its
metadata.

## Templates

`collections/list.html`, `collections/form.html`, `collections/detail.html`,
`documents/detail.html` and `documents/form.html`, all extending `base.html`. The sidebar
gains the *Collections* link, and the dashboard the links to create a collection, to open
the recent ones and to list them all.

## Tests

pytest:

- `test_web_collections.py` and `test_web_documents.py`: every route with mocked
  authentication, database, quotas and embeddings, including redirects,
  quota errors and failure handling.
- `unit/test_web_documents_chunking.py`: Markdown and even splitting.
- `unit/test_web_documents_create_routes.py`: chunked and uploaded creation.
- `test_web_collections.py` also covers a name whose slug is already used.

behave (`features/web_content.feature`): the real routes, templates and
document service run over the in-memory store with a fake embedder and a quota
service that can refuse.

- Pages require a signed-in user
- The collection list shows the collections of the workspace
- Another workspace's collections are not listed
- Creating a collection derives its slug from the name
- A collection is refused when the plan limit is reached
- Viewing a collection lists its documents
- Viewing an unknown collection goes back to the list
- Renaming a collection
- Deleting a collection deletes its documents
- Deleting selected documents
- Adding a document generates its embedding
- Long texts can be split by markdown sections
- Uploading a file records its name
- An empty document is refused
- A document is refused when the plan limit is reached
- Viewing a document
- Editing a document regenerates its embedding
- Deleting a document

browser (`features/browser/web_content.feature`, tag `@browser`): the pages in a real
Chromium, signed in through the fake OpenID provider, over a SQLite file where the
steps read back what the forms saved. The documents are embedded by the bag-of-words
model of the behave fakes, the native confirmation dialogs are accepted, and a file is
chosen in the upload field. Every link of the pages is followed to check that it leads
to a page.

- The collection list starts empty and offers to create a collection
- A collection is created from the form
- Two collections cannot share a name
- The plan limits the number of collections
- A collection is renamed
- A document is added to a collection
- A document needs some content
- A text file is uploaded as a document
- A document is read, edited and deleted
- Several documents are deleted at once
- A collection is deleted with its documents
- The collection of another workspace is out of reach
- The dashboard leads to the collection pages
- The collection pages only lead to pages that exist
