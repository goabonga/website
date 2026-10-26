# Chunked upload

Packages can be large and a reverse proxy may limit request bodies, so a
package can be sent in sequential chunks within an upload session. Once every
chunk has arrived the session is assembled and handed to the same upload
pipeline as `POST /api/packages`.

## Flow

1. `POST /api/upload/init` with `filename`, `total_size`, `total_chunks`,
   `suite`, `component` and `visibility` (default `private`). The answer holds
   the `upload_id` and the `chunk_size` the client should use
   (`UPLOAD_CHUNK_SIZE`).
2. `POST /api/upload/{upload_id}/chunk?index=N` with the chunk as the
   multipart field `chunk`. Indexes start at 0, may arrive in any order and
   each one is accepted once. The answer reports `received` and `total`.
3. `POST /api/upload/{upload_id}/complete` assembles the chunks and saves the
   package; the answer is the package, like the single-request upload.
4. `DELETE /api/upload/{upload_id}` cancels a session (204).

Callers are resolved like for apt clients: Basic or Bearer with a token, or the
web session cookie. A session user is already interactively authenticated, so
only API callers are checked against `apt:write` or `apt:write:<component>`.
Anonymous requests get 401.

Errors: 400 for a size above `UPLOAD_MAX_SIZE`, an index out of range, a
repeated chunk, missing chunks at completion, or an invalid package; 403 when
the session belongs to another user or the scope is missing; 404 for an
unknown session; 409 when the package already exists. The session directory is
removed after completion whatever the outcome.

## Storage

Sessions live under `<APT_REPO_ROOT>/.uploads/<upload_id>/` as
`manifest.json` (owner, target, received chunk indexes, creation time) and one
`chunk_NNNNNN` file per chunk. Sessions older than `UPLOAD_TTL` and
directories without a readable manifest are removed lazily whenever a new
session starts; no background job is involved.

## Settings

| Variable | Default | Description |
| --- | --- | --- |
| `UPLOAD_CHUNK_SIZE` | `5242880` | Chunk size advertised to clients (bytes) |
| `UPLOAD_MAX_SIZE` | `524288000` | Largest accepted package (bytes) |
| `UPLOAD_TTL` | `3600` | Age after which an unfinished session is cleaned (seconds) |

When nginx fronts the service, `client_max_body_size` must allow at least one
chunk, and the deployed value allows whole packages for the single-request
upload.

## Tests

- pytest: `tests/test_chunked_upload.py` (manifest, size limit, chunk
  ordering, range and duplicates, assembly, missing chunks, expiry and broken
  session cleanup) and `tests/test_api_upload.py` (authorization, session
  users, the full flow, visibility fallback, error mapping, ownership, cancel).
- behave: `features/chunked_upload.feature` with the scenarios "A package is
  uploaded in several chunks", "The upload cannot be completed while chunks
  are missing", "Another user cannot add chunks to my upload", "A cancelled
  upload cannot be completed", "Callers without a write scope cannot start an
  upload" and "Anonymous callers cannot start an upload".
