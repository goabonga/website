# Amazon SES webhook proxy

Adds the Amazon SES notification webhook. SES publishes bounce, complaint and
delivery events to an SNS topic, and SNS posts them to the gateway. The
gateway performs no SNS verification: subscription confirmation, signature
verification and event processing are delegated to the internal API. The
proxy pattern is the one described in the [Brevo page](04-brevo.md).

## What it does

`POST /webhooks/ses` (also `/webhooks/ses/`) forwards the raw SNS payload to
`/webhooks/ses` of the internal API.

Processing order of `webhooks.routes.ses.ses_webhook`:

1. **503** `Service unavailable` when neither `SES_INTERNAL_API_SOCKET` nor
   `SES_INTERNAL_API_URL` is set.
2. An empty body is acknowledged with **200** and nothing is forwarded.
3. The `Content-Type` of the incoming request is forwarded (SNS uses
   `text/plain`, which is also the default), together with the SNS headers
   present on the request: `x-amz-sns-message-type`, `x-amz-sns-message-id`,
   `x-amz-sns-topic-arn` and `x-amz-sns-subscription-arn`.
4. An `Authorization: Bearer ...` header is added when available (OAuth2
   token first, then `SES_INTERNAL_API_TOKEN`, see
   [OAuth2 client credentials](03-oauth2.md)).
5. The status and body of the internal API are relayed. Connection errors
   give **502** `Bad gateway`, other errors **500**.

There is no signature check at the gateway level, so no secret setting
exists for SES.

## Enabling the route

The router is registered with the prefix `/webhooks/ses` and the tag `ses`
only when `SES_ENABLED` is true; otherwise the path answers 404.

## Settings

| Variable | Default | Description |
| --- | --- | --- |
| `SES_ENABLED` | `false` | Register the `/webhooks/ses` route |
| `SES_INTERNAL_API_URL` | empty | HTTP URL of the internal API |
| `SES_INTERNAL_API_SOCKET` | empty | Unix socket of the internal API (overrides the URL) |
| `SES_INTERNAL_API_TOKEN` | empty | Static bearer token (also read from systemd credentials) |

## Data model

None.

## How it is tested

Pytest:

- `test_routes_ses.py` - internal client selection, 503 when unconfigured,
  empty body, forwarding of the body, content type and SNS headers, default
  content type, authorization header, status relay and the 502/500 paths.
- `test_main.py` (`TestSESRegistration`) and `test_config.py`
  (`TestSESSettings`) - registration flag, defaults and overrides.

Behave (`apps/webhooks/features/ses.feature`), with the internal API
mocked:

- Forward SNS subscription confirmation, delivery, bounce and complaint
  notifications, unsubscribe confirmation and configuration set events
- Empty body returns 200
- Forward any payload as raw proxy
- Forward or omit the Authorization header depending on the token
- Forward the SNS headers to the internal API
- Forward the raw body to the SES internal endpoint
- Bad gateway when the internal API cannot be reached
- Service unavailable when the internal API is not configured

```bash
uv run --package webhooks pytest apps/webhooks
uv run --package webhooks behave apps/webhooks/features
```
