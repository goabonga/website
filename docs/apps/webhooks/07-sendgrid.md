# SendGrid webhook proxy

Adds the SendGrid Event Webhook, with optional ECDSA signature verification
at the gateway. It is the only provider feature that needs the `cryptography`
library. The proxy pattern is the one described in the
[Brevo page](04-brevo.md).

## What it does

`POST /webhooks/sendgrid` (also `/webhooks/sendgrid/`) forwards the raw body
to `/webhooks/sendgrid` of the internal API.

Processing order of `webhooks.routes.sendgrid.sendgrid_webhook`:

1. **503** `Service unavailable` when neither `SENDGRID_INTERNAL_API_SOCKET`
   nor `SENDGRID_INTERNAL_API_URL` is set.
2. An empty body is acknowledged with **200** and nothing is forwarded.
3. If `SENDGRID_WEBHOOK_VERIFICATION_KEY` is set, the request is verified
   with `verify_sendgrid_signature`: the base64 ECDSA (SHA-256) signature in
   `X-Twilio-Email-Event-Webhook-Signature` must be valid for the
   concatenation of the `X-Twilio-Email-Event-Webhook-Timestamp` header and
   the raw body, using the PEM public key. A missing header, a bad
   signature, a malformed key or a key that is not an elliptic curve key all
   fail the verification and are answered with **401** `Invalid signature`.
   Without a key the check is skipped.
4. The body is forwarded with `Content-Type: application/json`, the two
   signature headers when present (so the internal API can verify them as
   well) and, when available, an `Authorization: Bearer ...` header (OAuth2
   token first, then `SENDGRID_INTERNAL_API_TOKEN`, see
   [OAuth2 client credentials](03-oauth2.md)).
5. The status and body of the internal API are relayed. Connection errors
   give **502** `Bad gateway`, other errors **500**.

## Enabling the route

The router is registered with the prefix `/webhooks/sendgrid` and the tag
`sendgrid` only when `SENDGRID_ENABLED` is true; otherwise the path answers
404.

## Settings

| Variable | Default | Description |
| --- | --- | --- |
| `SENDGRID_ENABLED` | `false` | Register the `/webhooks/sendgrid` route |
| `SENDGRID_WEBHOOK_VERIFICATION_KEY` | empty | ECDSA public key in PEM format; verification runs only when set |
| `SENDGRID_INTERNAL_API_URL` | empty | HTTP URL of the internal API |
| `SENDGRID_INTERNAL_API_SOCKET` | empty | Unix socket of the internal API (overrides the URL) |
| `SENDGRID_INTERNAL_API_TOKEN` | empty | Static bearer token for the internal API |

The verification key and the token can be provided as systemd credentials.

## Data model

None.

## How it is tested

Pytest:

- `test_routes_sendgrid.py` - signature verification with a real ECDSA key
  (valid, invalid, missing signature or timestamp, non-ECDSA key, other
  errors), internal client selection, 503, empty body, header and
  body forwarding, authorization header, status relay and the 502/500 paths.
- `test_main.py` (`TestSendGridRegistration`) and `test_config.py`
  (`TestSendGridSettings`) - registration flag, defaults and overrides.

Behave (`apps/webhooks/features/sendgrid.feature`). The scenarios generate
an ECDSA key pair in-process and sign the payload for real; the internal API
is mocked:

- Forward bounce, spam report, delivered and multiple events
- Empty body returns 200
- Reject an invalid signature, a missing signature or a signature made with
  another key when a verification key is configured
- Accept a valid signature when a verification key is configured
- Forward or omit the Authorization header depending on the token
- Forward the raw body to the SendGrid internal endpoint
- Bad gateway when the internal API cannot be reached
- Service unavailable when the internal API is not configured

```bash
uv run --package webhooks pytest apps/webhooks
uv run --package webhooks behave apps/webhooks/features
```
