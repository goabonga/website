# Stripe webhook proxy

Adds the Stripe webhook. The gateway forwards the payload and the
`Stripe-Signature` header untouched: signature verification is done by the
billing service (the internal API), which holds the Stripe signing secret.
The proxy pattern is the one described in the [Brevo page](04-brevo.md).

## What it does

`POST /webhooks/stripe` (also `/webhooks/stripe/`) forwards the raw body to
`/webhooks/stripe` of the internal API.

Processing order of `webhooks.routes.stripe.stripe_webhook`:

1. **503** `Service unavailable` when neither `STRIPE_INTERNAL_API_SOCKET`
   nor `STRIPE_INTERNAL_API_URL` is set.
2. An empty body is acknowledged with **200** and nothing is forwarded.
3. The request is forwarded with `Content-Type: application/json`, the
   incoming `Stripe-Signature` header (empty string when absent) and, when
   available, an `Authorization: Bearer ...` header (OAuth2 token first,
   then `STRIPE_INTERNAL_API_TOKEN`, see
   [OAuth2 client credentials](03-oauth2.md)).
4. The status and body of the internal API are relayed. Connection errors
   give **502** `Bad gateway`, other errors **500**.

The gateway has no Stripe secret: no signature is verified here.

The signature is the only authentication of the endpoint at billing: it
ignores the bearer token the gateway sends, unless billing sets
`STRIPE_WEBHOOK_REQUIRED_SCOPE`, in which case the token must carry that
scope (see the [billing deployment](../billing/15-deployment.md)).

## Enabling the route

The router is registered with the prefix `/webhooks/stripe` and the tag
`stripe` only when `STRIPE_ENABLED` is true; otherwise the path answers 404.

## Settings

| Variable | Default | Description |
| --- | --- | --- |
| `STRIPE_ENABLED` | `false` | Register the `/webhooks/stripe` route |
| `STRIPE_INTERNAL_API_URL` | empty | HTTP URL of the internal API |
| `STRIPE_INTERNAL_API_SOCKET` | empty | Unix socket of the internal API (overrides the URL) |
| `STRIPE_INTERNAL_API_TOKEN` | empty | Static bearer token (also read from systemd credentials) |

## Data model

None.

## How it is tested

Pytest:

- `test_routes_stripe.py` - internal client selection, 503 when
  unconfigured, empty body, forwarding of body and `Stripe-Signature`,
  authorization header, status relay and the 502/500 paths.
- `test_main.py` (`TestStripeRegistration`) and `test_config.py`
  (`TestStripeSettings`) - registration flag, defaults and overrides.

Behave (`apps/webhooks/features/stripe.feature`), with the internal API
mocked:

- Forward payment intent, checkout session and invoice events
- Empty body returns 200
- Forward or omit the Authorization header depending on the token
- Forward the Stripe signature to the internal API
- Forward the raw body to the Stripe internal endpoint
- Relay the status of the internal API
- Bad gateway when the internal API cannot be reached
- Service unavailable when the internal API is not configured

```bash
uv run --package webhooks pytest apps/webhooks
uv run --package webhooks behave apps/webhooks/features
```
