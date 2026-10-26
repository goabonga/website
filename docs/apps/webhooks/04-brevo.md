# Brevo webhook proxy

The first provider feature. It introduces the raw proxy pattern shared by all
providers and adds the Brevo (Sendinblue) email event webhook, with optional
HMAC signature verification at the gateway.

## What it does

`POST /webhooks/brevo` (the trailing-slash form `/webhooks/brevo/` is also
accepted) receives a Brevo webhook and forwards the original body, as is, to
the internal API. No payload is parsed or transformed.

Processing order of `webhooks.routes.brevo.brevo_webhook`:

1. If neither `BREVO_INTERNAL_API_SOCKET` nor `BREVO_INTERNAL_API_URL` is set,
   answer **503** `Service unavailable`.
2. An empty body is acknowledged with **200** and nothing is forwarded.
3. If `BREVO_WEBHOOK_SECRET` is set, the header `X-Sib-Webhook-Signature`
   must contain the hex HMAC-SHA256 of the raw body keyed with the secret
   (`verify_brevo_signature`, constant-time comparison). A missing or wrong
   signature is answered with **401** `Invalid signature`. Without a secret
   the check is skipped and the payload is forwarded unverified.
4. The body is POSTed to `/api/v1/webhooks/brevo` of the internal API with
   `Content-Type: application/json` and, when available, an `Authorization:
   Bearer ...` header built by the
   [OAuth2 client credentials](03-oauth2.md) feature (OAuth2 token first,
   then `BREVO_INTERNAL_API_TOKEN`). The timeout is 30 seconds.
5. The status code and body of the internal API are returned as is.
   A connection error becomes **502** `Bad gateway`, any other error
   **500** `Internal server error`.

The internal API is reached through `get_internal_client()`: a Unix socket
when `BREVO_INTERNAL_API_SOCKET` is set (it wins over the URL), otherwise the
HTTP base URL `BREVO_INTERNAL_API_URL`.

## Enabling the route

The route exists only when `BREVO_ENABLED` is true: `webhooks.main` imports
and registers the router (prefix `/webhooks/brevo`, tag `brevo`) at start-up
based on the settings. When disabled the path answers 404.

## Settings

| Variable | Default | Description |
| --- | --- | --- |
| `BREVO_ENABLED` | `false` | Register the `/webhooks/brevo` route |
| `BREVO_WEBHOOK_SECRET` | empty | HMAC-SHA256 secret; verification runs only when set |
| `BREVO_INTERNAL_API_URL` | empty | HTTP URL of the internal API |
| `BREVO_INTERNAL_API_SOCKET` | empty | Unix socket of the internal API (overrides the URL) |
| `BREVO_INTERNAL_API_TOKEN` | empty | Static bearer token for the internal API |

`BREVO_WEBHOOK_SECRET` and `BREVO_INTERNAL_API_TOKEN` can be provided as
systemd credentials (see [OAuth2 client credentials](03-oauth2.md)).

## Data model

None.

## How it is tested

Pytest:

- `test_routes_brevo.py` - signature verification (valid, invalid, missing,
  internal error), internal client selection (socket, URL, priority, error),
  and the handler: 503 when unconfigured, empty body, signature outcomes,
  header and body forwarding, authorization header, status relay and the
  502/500 error paths.
- `test_main.py` (`TestBrevoRegistration`) - the route is absent by default
  and registered when `BREVO_ENABLED` is true.
- `test_config.py` (`TestBrevoSettings`) - defaults and environment
  overrides.

Behave (`apps/webhooks/features/brevo.feature`). Every provider route is
enabled for the behave run and the internal API client is replaced by a mock,
so no network is involved:

- Forward delivered, hard bounce, soft bounce and complaint events
- Empty body returns 200
- Reject invalid signature, or a missing one, when secret is configured
- Accept valid signature when secret is configured
- Forward or omit the Authorization header depending on the token
- Forward the raw body to the Brevo internal endpoint
- Relay the status of the internal API
- Bad gateway when the internal API cannot be reached
- Service unavailable when the internal API is not configured

```bash
uv run --package webhooks pytest apps/webhooks
uv run --package webhooks behave apps/webhooks/features
```
