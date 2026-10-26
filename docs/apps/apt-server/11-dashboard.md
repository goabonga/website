# Package dashboard

The browser counterpart of the package API: signed-in users upload, share,
change the visibility of and delete their packages. All routes sit under
`/dashboard`, are hidden from OpenAPI, and require a session or other
credentials; an anonymous visitor is redirected (302) to `/login`.

## Pages and actions

| Route | Description |
| --- | --- |
| `GET /dashboard` | The caller own packages, filters `suite`, `component`, `q`, 25 per page |
| `GET /dashboard/upload` | Upload form |
| `POST /dashboard/upload` | Single request upload (`deb`, `suite`, `component`, `visibility`); 303 to `/dashboard`, or the form again with 400 (invalid package) or 409 (already exists) |
| `POST /dashboard/{id}/delete` | Delete the package, its grants and its pool file; 303 to `/dashboard` |
| `POST /dashboard/{id}/visibility` | Set `public`, `private` or `shared` (other values are ignored); 303 to the share page |
| `GET /dashboard/{id}/share` | Visibility and grants of a package |
| `POST /dashboard/{id}/share` | Grant `read` or `write` to a user (`sub` or email) or a group; 303 back, or the page with 409 when the grant exists |
| `POST /dashboard/{id}/revoke/{acl_id}` | Remove a grant; 404 for an unknown entry |

Management actions are allowed to whoever `can_write` the package: the
owner, an administrator, or a user holding a `write` grant (403 otherwise,
404 for an unknown package). Every mutation clears the index cache.

The upload page drives the chunked upload API from JavaScript: it splits the
file by the chunk size advertised by the server (`UPLOAD_CHUNK_SIZE`) and shows
a progress bar. `POST /dashboard/upload` is the plain form submission that
shares the `save_upload` pipeline with the API. Session users are not checked
against the `apt:write` scopes: being signed in and owning the package is
enough.

The sidebar of the layout gains "My Packages" and "Upload" for signed-in
users, and the package detail page offers "Share / Manage access" and
"Delete" to the owner and administrators.

The labels of the upload and share forms are bound to their controls
(`for`/`id`), so that a control can be reached by its label.

Reloading the package after a rejected duplicate grant is covered by a
dedicated fix: the rollback expires the loaded rows, which otherwise made the
share page fail with a lazy loading error instead of reporting the conflict.

## Settings

The page uses `UPLOAD_CHUNK_SIZE` and the repository settings; no new
variable is introduced.

## Tests

- pytest: `tests/test_dashboard.py` (login redirect, listing, filters and
  pagination, upload success and failures, session users, delete, visibility,
  share to a user and a group, duplicate grants, revoke, grantee permissions,
  owner controls on the package page) against SQLite.
- behave: `features/dashboard.feature` with the scenarios "Visitors are sent
  to the login page", "Users upload a package from the form", "The dashboard
  only lists my own packages", "Sharing a package grants access to another
  user", "Sharing twice with the same user reports a conflict", "Users cannot
  delete packages they do not own" and "Owners delete their package".
- browser: `features/browser/dashboard.feature` drives the dashboard in
  Chromium: "A visitor is sent to the identity provider", "The dashboard only
  lists the packages of the signed-in user", "The dashboard can be filtered by
  name", "A package is uploaded in chunks" (the JavaScript of the upload page
  sends the file in as many chunks as `UPLOAD_CHUNK_SIZE` requires), "A file
  that is not a package is reported", "The owner reaches the share page from
  the package page", "Other users get no controls on the package page", "A
  package is shared with another user", "Sharing twice with the same user
  reports a conflict", "The user a package is shared with can read it", "Access
  is revoked after a confirmation", "The visibility of a package is changed",
  "A package is deleted after a confirmation" and "Cancelling the confirmation
