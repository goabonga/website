# APT indexes

Debian clients read three kinds of metadata: `Packages` (one stanza per
package), `Release` (checksums of every `Packages` file) and the signatures of
`Release`. This feature renders them from the catalog, per caller. The HTTP
routes that serve them come with the next feature.

## What it does

- `apt_server.repo.indexes` renders a `Packages` stanza from a package row:
  usual control fields first in `dpkg-deb --field` order, any other control
  field alphabetically, then the repository-computed `Filename`, `Size`,
  `MD5sum`, `SHA1` and `SHA256`. Control keys that collide with these
  computed fields are dropped, so the stored control stanza can never override
  them. Stanzas are separated by a blank line, and `gzip_packages` produces
  deterministic output (no name or timestamp in the header).
- `apt_server.repo.release` renders `Release` with `Origin`, `Label`,
  `Suite`, `Codename`, `Date`, `Architectures`, `Components` and the MD5Sum,
  SHA1 and SHA256 sections listing every index sorted by path. It signs the
  result with the local `gpg` binary: `sign_clearsigned` for `InRelease`
  and `sign_detached` for `Release.gpg`. When `APT_GPG_KEY_ID` is empty the
  clear-signed form is the plain `Release` and the detached signature is
  empty, which is meant for tests and local development only.
- `apt_server.services.indexes` composes both from the database:
  - `render_packages` selects the packages of a suite, component and
    architecture (plus architecture `all`) that pass the package visibility
    filter of the caller, so a package absent from the caller view is absent
    from the index.
  - `render_release` lists the public components for anonymous callers. For
    authenticated callers a private component appears only when it holds at
    least one package they can see, so the existence of private components is
    not disclosed.
  - Every rendered `Packages` variant (plain or gzip) is cached in the
    `index_cache` table, keyed by a hash of caller, groups, suite, component,
    architecture and compression. Entries older than `APT_INDEX_CACHE_TTL`
    seconds are dropped on read (a TTL of `0` or less never expires them), and
    `invalidate_index_cache` wipes the whole cache after any change that can
    alter a caller view (upload, delete, visibility or ACL change).

## Settings

| Variable | Default | Description |
| --- | --- | --- |
| `APT_SUITES` | `stable` | Comma-separated suites |
| `APT_ARCHITECTURES` | `amd64` | Comma-separated architectures |
| `APT_ORIGIN` | `apt-server` | `Origin:` field of `Release` |
| `APT_LABEL` | `apt-server` | `Label:` field of `Release` |
| `APT_GPG_KEY_ID` | empty | Key used to sign `Release`; empty disables signing |
| `APT_INDEX_CACHE_TTL` | `60` | Lifetime of a rendered index (seconds) |

Signing runs `/usr/bin/gpg` with `--batch --pinentry-mode loopback`, so the
private key never enters the Python process and the key must be available in
the keyring of the service user.

## Tests

- pytest: `tests/test_repo_indexes.py` (stanza ordering and computed headers,
  gzip determinism, `Release` content, signing with and without a key, gpg
  invoked through a fake `subprocess.run`) and `tests/test_service_indexes.py`
  (per-caller filtering, component filtering, cache reuse, invalidation, TTL
  expiry, one cache row per caller and variant, `Release` component
  visibility), the latter against SQLite.
- behave: `features/apt_indexes.feature` with the scenarios "Anonymous callers
  get an index of public packages", "Owners see their private packages in the
  index", "Index entries carry the pool location and checksums", "The
  compressed index matches the plain index", "A newly added package appears
  once the cache is invalidated", "Release for anonymous callers hides private
  components" and "Release for the owner exposes components holding visible
  packages".
