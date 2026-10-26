# Package API

The JSON API used by CI jobs and administrators to upload `.deb` files, list
and update packages, and manage who may read or write them. Every endpoint
requires a bearer token (see the OIDC authentication page).

## Endpoints

| Endpoint | Scope or rule | Description |
| --- | --- | --- |
| `POST /api/packages` | `apt:write` or `apt:write:<component>` | Upload a `.deb` (multipart: `deb`, `suite`, `component`, `visibility`) |
| `GET /api/packages` | any authenticated user | List visible packages; filters `suite`, `component`, `name` |
| `GET /api/packages/{id}` | `can_read` | Package metadata; 404 when hidden |
| `PATCH /api/packages/{id}` | `can_write` | Change `visibility` and `description` |
| `DELETE /api/packages/{id}` | `can_write` | Delete the row, its ACL entries and the pool file |
| `GET /api/packages/{id}/acl` | owner or admin | List grants |
| `POST /api/packages/{id}/acl` | owner or admin | Grant `read` or `write` to a user or a group |
| `DELETE /api/packages/{id}/acl/{acl_id}` | owner or admin | Revoke a grant |
| `POST /api/reindex` | `apt:admin` | Drop every cached `Packages` rendering (204) |

`POST /api/packages` answers 201 with the package, 400 for an invalid
archive, an unknown suite, an unsupported architecture or an unknown
component, 403 for a missing scope and 409 when the same name, version,
architecture, suite and component already exist. The caller becomes the owner
and `visibility` defaults to `private`.

An ACL grant needs exactly one of `grantee_user_id` and `grantee_group`
(400 otherwise) and a duplicate grant answers 409. A package whose component
is no longer in `APT_COMPONENTS` answers 410.

Every mutation that can change what a caller sees (upload, update, delete,
grant, revoke) clears the index cache, so the next `apt update` reflects it.
`reindex` is an escape hatch after out-of-band changes such as a key rotation.

## Upload pipeline

`apt_server.services.upload.save_upload` is shared by the API and, later, by
the web UI:

1. the body is staged in a temporary file, removed at the end whatever the
   outcome;
2. `apt_server.repo.debfile.parse_deb` reads the control stanza with
   `python-debian` and computes size, MD5, SHA-1 and SHA-256 (it rejects files
   that are not archives or lack `Package`, `Version` or `Architecture`);
3. the suite, component and architecture (`all` is always accepted) are
   checked against the settings;
4. an existing row with the same identity raises a conflict;
5. `apt_server.repo.pool.write_deb` moves the file to
   `<APT_REPO_ROOT>/pool/<component>/<prefix>/<name>/<name>_<version>_<arch>.deb`
   (`<prefix>` is the first letter, or four letters for `lib*` packages). An
   identical file is kept in place, a file with other content is refused;
6. the row is inserted and the index cache cleared. If a concurrent upload won
   the race (integrity error) the pool file is removed and a conflict is
   reported.

`apt_server.services.caller.caller_from_auth` converts the authenticated user
into the `Caller` used by the ACL rules (scopes, groups, email as display name).

## Settings

| Variable | Default | Description |
| --- | --- | --- |
| `APT_REPO_ROOT` | `/var/lib/apt-server` | Root of the pool; the service needs read and write access, nginx read access |

## Dependencies

`python-debian` (archive parsing) and `python-multipart` (form uploads) are
added by this feature.

## Tests

The `.deb` fixtures are built by `tests/debfactory.py`, a pure Python `ar`
writer, so no `dpkg-deb` binary is needed.

- pytest: `tests/test_repo_debfile.py`, `tests/test_repo_pool.py`,
  `tests/test_service_upload.py` (storage, validation, conflicts, cache
  invalidation, temporary files) and `tests/test_api_packages.py` (every
  endpoint, scope rules, ownership, ACL management, reindex) against SQLite.
- behave: `features/package_api.feature` with the scenarios "A writer uploads
  a package", "A reader cannot upload", "A component scoped writer is limited
  to its component", "Uploading the same version twice is a conflict", "A file
  that is not a Debian package is rejected", "Private packages are only listed
  for their owner", "Granting read access shares a package", "Making a package
  public exposes it to everyone", "Only the owner can delete a package" and
  "Only administrators can reindex".
