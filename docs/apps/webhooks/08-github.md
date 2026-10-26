# GitHub webhook proxy

Adds the GitHub repository event webhook, with optional HMAC-SHA256
signature verification at the gateway. The downstream handling of GitHub
events is a placeholder in the internal services; the gateway part is
complete. The proxy pattern is the one described in the
[Brevo page](04-brevo.md).

## What it does

`POST /webhooks/github` (also `/webhooks/github/`) forwards the raw body to
`/webhooks/github` of the internal API.

Processing order of `webhooks.routes.github.github_webhook`:

1. **503** `Service unavailable` when neither `GITHUB_INTERNAL_API_SOCKET`
   nor `GITHUB_INTERNAL_API_URL` is set.
2. An empty body is acknowledged with **200** and nothing is forwarded.
3. If `GITHUB_WEBHOOK_SECRET` is set, the header `X-Hub-Signature-256` must
   be `sha256=` followed by the hex HMAC-SHA256 of the raw body keyed with
   the secret (`verify_github_signature`, constant-time comparison). A
   missing header, a value without the `sha256=` prefix or a wrong digest is
   answered with **401** `Invalid signature`. Without a secret the check is
   skipped.
4. The body is forwarded with `Content-Type: application/json`, the headers
   `X-Hub-Signature-256`, `X-GitHub-Event` and `X-GitHub-Delivery` when
   present on the request and, when available, an `Authorization: Bearer
   ...` header (OAuth2 token first, then `GITHUB_INTERNAL_API_TOKEN`, see
   [OAuth2 client credentials](03-oauth2.md)).
5. The status and body of the internal API are relayed. Connection errors
   give **502** `Bad gateway`, other errors **500**.

## Enabling the route

The router is registered with the prefix `/webhooks/github` and the tag
`github` only when `GITHUB_ENABLED` is true; otherwise the path answers 404.

## Settings

| Variable | Default | Description |
| --- | --- | --- |
| `GITHUB_ENABLED` | `false` | Register the `/webhooks/github` route |
| `GITHUB_WEBHOOK_SECRET` | empty | HMAC-SHA256 secret; verification runs only when set |
| `GITHUB_INTERNAL_API_URL` | empty | HTTP URL of the internal API |
| `GITHUB_INTERNAL_API_SOCKET` | empty | Unix socket of the internal API (overrides the URL) |
| `GITHUB_INTERNAL_API_TOKEN` | empty | Static bearer token for the internal API |

The secret and the token can be provided as systemd credentials.

## Data model

None.

## How it is tested

Pytest:

- `test_routes_github.py` - signature verification (valid, invalid, missing,
  wrong prefix, internal error), internal client selection, 503, empty
  body, GitHub header forwarding, authorization header, status relay and the
  502/500 paths.
- `test_main.py` (`TestGitHubRegistration`) and `test_config.py`
  (`TestGitHubSettings`) - registration flag, defaults and overrides.

Behave (`apps/webhooks/features/github.feature`), with the internal API
mocked:

- Forward push, pull request and release events
- Empty body returns 200
- Reject an invalid or missing signature when a secret is configured
- Accept a valid signature when a secret is configured
- Forward or omit the Authorization header depending on the token
- Forward the GitHub headers to the internal API
- Forward the raw body to the GitHub internal endpoint
- Bad gateway when the internal API cannot be reached
- Service unavailable when the internal API is not configured

```bash
uv run --package webhooks pytest apps/webhooks
uv run --package webhooks behave apps/webhooks/features
```
