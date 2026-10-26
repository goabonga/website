# MCP releases and downloads

The Knowledge MCP is a standalone executable that lets AI agents use the
service. Its releases are published on GitHub; this feature mirrors them in
the database through a GitHub webhook and exposes a public API to list and
download them.

## GitHub release webhook

`POST /webhooks/github/releases` is served by the internal sub-application
(tag `Webhooks`).

- When `GITHUB_WEBHOOK_SECRET` is set, `X-Hub-Signature-256` must contain
  `sha256=<hex HMAC-SHA256 of the body>`; a missing or wrong signature is a
  `401`. Without a secret, events are accepted unsigned.
- Only `X-GitHub-Event: release` events are processed; any other event
  answers `{"status": "ignored"}`. Likewise for release actions other than
  `published`, `edited` and `released`.
- A body that is not a valid release event answers `400`.

For a processed event, `process_release`:

1. strips a leading `v` from the tag to get the version;
2. creates the `mcp_releases` row, or updates it when the GitHub release id is
   already known (version, notes, status, publication date). A GitHub draft is
   stored with status `draft`, anything else as `published`;
3. detects the platform of each asset from its file name and creates or
   updates the matching `mcp_release_assets` row (file name, download URL,
   size). Files with an unknown platform, such as checksum files, are skipped.

| File name contains | Platform |
| --- | --- |
| `linux` and `x86_64` or `amd64` | `linux-x86_64` |
| `linux` and `arm64` or `aarch64` | `linux-arm64` |
| `macos` or `darwin`, and `x86_64` or `amd64` | `macos-x86_64` |
| `macos` or `darwin`, and `arm64` or `aarch64` | `macos-arm64` |
| `windows` or `.exe`, and `x86_64`, `amd64` or `win64` | `windows-x86_64` |

The response is `{"status": "ok", "release": {"version", "status"}}`.

## Public API

Tagged `MCP Downloads`, no authentication.

| Method | Path | Description |
| --- | --- | --- |
| `GET` | `/api/v1/mcp/releases` | Published releases, newest first, with their platforms (`include_deprecated=true` adds deprecated ones; drafts are never listed). |
| `GET` | `/api/v1/mcp/releases/latest` | Latest published release with its assets (file name, URL, size, SHA-256, download count). `404` when there is none. |
| `GET` | `/api/v1/mcp/releases/{version}` | One release; a leading `v` is accepted. |
| `GET` | `/api/v1/mcp/download/{version}/{platform}` | `302` redirect to the asset URL; increments the download counter. |
| `GET` | `/api/v1/mcp/download/latest/{platform}` | Same for the latest published release. |

An unknown platform value is a `400` that lists the valid ones
(`linux-x86_64`, `linux-arm64`, `macos-x86_64`, `macos-arm64`,
`windows-x86_64`); an unknown release, or a release without an asset for the
platform, is a `404`. The `latest` download route is declared before the
versioned one, otherwise `latest` would be read as a version.

## Settings

| Variable | Default | Description |
| --- | --- | --- |
| `GITHUB_WEBHOOK_SECRET` | empty | Shared secret that signs GitHub webhook payloads. |

## Tests

pytest:

- `test_mcp_downloads.py`: every download route with a mocked session,
  including a regression test for the `latest` download path.
- `test_github_webhook_routes.py`: signature checks, event filtering, payload
  errors and release processing through the endpoint.
- `unit/test_github_webhooks.py`: signature verification, platform detection
  and version parsing.

behave (`features/releases.feature`): the routes and the webhook processing
are real; the database is an in-memory store that evaluates the SELECT
statements they issue.

- A published GitHub release is imported
- An edited release updates the existing one
- A draft release is stored but not listed
- Events other than releases are ignored
- Release actions other than publication are ignored
- A bad signature is rejected
- A missing signature is rejected
- A malformed release payload is rejected
- List published releases, newest first
- Get the latest release
- Get a release by version with or without the v prefix
- An unknown release is not found
- Downloading redirects to the asset and counts the download
- Downloading the latest release for a platform
- An unknown platform is rejected
- A platform without asset is not found
