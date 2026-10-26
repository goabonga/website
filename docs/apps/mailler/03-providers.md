# Email providers

Delivery adapters for four email providers, a factory that instantiates the
configured ones, the HMAC helpers used to sign provider callbacks and
unsubscribe links, and the endpoint that lists the usable providers.

## Providers

All adapters implement `EmailProvider` (`send_email(...)` returning an
`EmailResult` with `success`, `provider_message_id` and `error_message`).
A provider is usable only when its credentials are configured
(`is_configured`).

| Name | Transport | Configured when |
| --- | --- | --- |
| `brevo` | HTTPS call to the Brevo transactional API | `BREVO_API_KEY` is set |
| `sendgrid` | HTTPS call to the SendGrid v3 mail API | `SENDGRID_API_KEY` is set |
| `ses` | AWS SES through `boto3` | `SES_ACCESS_KEY`, `SES_SECRET_KEY` and `SES_REGION` are set |
| `protonmail` | SMTP with STARTTLS to a Protonmail Bridge | host, port, `PROTONMAIL_USER` and `PROTONMAIL_PASSWORD` are set |

`mailler.services.providers.get_provider(name)` returns a cached instance and
raises `ValueError` for an unknown or unconfigured provider.
`get_available_providers()` returns the names of the configured providers.

The Brevo adapter also exposes `unblock_contact` and `get_contact_status`
helpers (used by the contacts feature) and attaches a signed
`X-Mailin-custom` header to every message so that Brevo callbacks can be
authenticated later (see the webhooks feature).

## Signatures

`mailler.services.webhook_signature` signs identifiers with HMAC-SHA256 using
`WEBHOOK_HMAC_SECRET`:

- `generate_webhook_signature` / `verify_webhook_signature` for delivery
  callbacks (signature over the email id and the recipient).
- `build_mailin_custom` / `parse_mailin_custom` for the `X-Mailin-custom`
  header value (`email_id:...,signature:...,key:value`, with commas and
  colons escaped in values).
- `generate_unsubscribe_signature` / `verify_unsubscribe_signature` and
  `build_unsubscribe_url` for unsubscribe links built from
  `UNSUBSCRIBE_BASE_URL`. The signature covers the client owning the contact
  as well as the address, so a link only unsubscribes the contact of that
  client.

Without `WEBHOOK_HMAC_SECRET`, delivery callbacks are not signed and are
accepted unsigned, whereas unsubscribe signatures are always rejected.

## Endpoint

| Endpoint | Method | Scope | Description |
| --- | --- | --- | --- |
| `/api/v1/providers` | GET | `mailler:read` | `{"providers": [...]}` listing the configured providers |

## Settings

| Variable | Default | Description |
| --- | --- | --- |
| `DEFAULT_FROM` | empty | Optional platform sender address, used only when a caller provides none |
| `DEFAULT_FROM_NAME` | empty | Optional platform sender name |
| `BREVO_API_KEY` | empty | Brevo API key (secret) |
| `SENDGRID_API_KEY` | empty | SendGrid API key (secret) |
| `SES_REGION` | empty | AWS SES region (SES is not available until it is set) |
| `SES_ACCESS_KEY` | empty | AWS access key (secret) |
| `SES_SECRET_KEY` | empty | AWS secret key (secret) |
| `PROTONMAIL_HOST` | empty | Protonmail Bridge SMTP host |
| `PROTONMAIL_PORT` | `0` | Protonmail Bridge SMTP port |
| `PROTONMAIL_USER` | empty | Bridge user |
| `PROTONMAIL_PASSWORD` | empty | Bridge password (secret) |
| `WEBHOOK_HMAC_SECRET` | empty | Shared secret for signatures (secret) |
| `UNSUBSCRIBE_BASE_URL` | empty | Base URL used to build unsubscribe links |

The secrets above can be supplied as systemd credentials, like
`OAUTH2_CLIENT_SECRET` (see [OAuth2 authentication](02-authentication.md)).

## Dependencies

`boto3` (SES) and `httpx` (Brevo and SendGrid) are used by the adapters. The
Protonmail adapter uses the standard library `smtplib`.

## How it is tested

- pytest: `tests/test_services_providers_base.py`, `..._brevo.py`,
  `..._sendgrid.py`, `..._ses.py`, `..._protonmail.py`, `..._factory.py`
  (all under `tests/`), `tests/test_services_webhook_signature.py`,
  `tests/test_routes_providers.py`, plus settings cases in
  `tests/test_config.py`. Provider calls are mocked.
- behave: `features/providers.feature` (listing configured providers,
  authentication and scope, factory lookup errors, signature and custom
  header round trips). Settings are overridden per scenario; no provider API
  is contacted.
