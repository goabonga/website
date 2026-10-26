# Brevo delivery webhooks

Brevo reports what happened to the messages it delivered (delivered, bounced,
opened, clicked, ...). The platform webhooks service forwards those events to
mailler, which updates the stored emails and the campaign counters.

## Endpoint

| Endpoint | Method | Scope | Description |
| --- | --- | --- | --- |
| `/api/v1/webhooks/brevo` | POST | `mailler:webhooks` | Process one Brevo event |

The caller is a machine client of the identity provider holding the
`mailler:webhooks` scope. The body is the JSON event sent by Brevo.

- An empty body, or an event without an `email`, is acknowledged with `200`
  and ignored. Invalid JSON gives `400`; an unexpected failure `500`.
- The `X-Mailin-custom` field carries `email_id`, `signature` and, for
  campaign emails, `campaign_id` (written when the message was sent, see
  [Email providers](03-providers.md)). When `WEBHOOK_HMAC_SECRET` is set the
  signature over the email id and the recipient is mandatory: a missing or
  invalid one gives `401` and nothing is changed. Without a secret, events
  are accepted unsigned.

## Event handling

| Brevo event | Email status | Campaign tracking |
| --- | --- | --- |
| `delivered` | `delivered` (`delivered_at`) | `sent` send becomes `delivered`, `delivered_count` + 1 |
| `hard_bounce`, `blocked`, `invalid` | `bounced` with the reason (`bounced_at`) | send becomes `bounced`, `bounced_count` + 1, an active contact becomes `bounced` |
| `soft_bounce` | `bounced` only if the reason looks permanent (it mentions `mx`, `domain`, `invalid`, `not exist` or `unknown`); temporary soft bounces are only logged | same as a hard bounce when permanent |
| `complaint` | `bounced` with the reason "Spam complaint" | send becomes `complained`, `complained_count` + 1, an active contact becomes `complained` |
| `unsubscribe`, `unsubscribed` | unchanged | campaign tracking only |
| `open`, `unique_opened` | unchanged | `delivered` send becomes `opened`, `opened_count` + 1 |
| `click` | unchanged | send becomes `clicked`, `clicked_count` + 1 |
| `request` | unchanged | none |

Unknown event types are acknowledged and ignored.

Events are applied directly to the database; they are not forwarded to
another service.

## How it is tested

- pytest: `tests/test_routes_webhooks.py` (every event type, signature
  checks, status updates, campaign counters, error branches), plus the
  `webhook_client` fixture in `tests/conftest.py`.
- behave: `features/webhooks.feature` covers each event type, invalid and
  empty payloads, authentication and scope, and a second group of scenarios
  that enable signature checking, seed emails in the in-process SQLite
  database and check the stored status after signed, forged and unsigned
  events.
