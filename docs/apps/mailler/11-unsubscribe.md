# Public unsubscribe

Recipients can opt out of future emails through a signed link, without any
authentication. The link is built from the recipient address, the client that
owns the contact and an HMAC signature (see
[Email providers](03-providers.md)), so it cannot be forged or reused for
another address or another client: the same address can be a contact of
several clients and a link only unsubscribes the one of the client that sent
the email.

## Endpoints

Both endpoints are public (no bearer token) and live under `/api/v1`.

| Endpoint | Method | Description |
| --- | --- | --- |
| `/api/v1/unsubscribe?email=...&client=...&sig=...` | GET | HTML confirmation page with an "Unsubscribe from emails" button |
| `/api/v1/unsubscribe?email=...&client=...&sig=...` | POST | Unsubscribes the contact and returns an HTML confirmation |

Both require the `email`, `client` and `sig` query parameters (`422` when
missing). The confirmation form submits the same three parameters in its
action.

## Behaviour

- The signature is verified first. An invalid signature, a signature issued
  for another address or another client, or a service without `WEBHOOK_HMAC_SECRET` gives a
  `403` page titled "Unsubscribe failed" and changes nothing.
- On `POST`, the contact of that client with that address (case-insensitive)
  is set to `unsubscribed`. If the contact is unknown or already unsubscribed the page
  still reports success, so the endpoint does not reveal which addresses are
  stored.
- `mailler.services.webhook_signature.build_unsubscribe_url` produces the
  link from `UNSUBSCRIBE_BASE_URL`; campaign emails (see the campaigns
  page) embed it.

## Settings

| Variable | Description |
| --- | --- |
| `WEBHOOK_HMAC_SECRET` | Secret used to sign and verify the links (required) |
| `UNSUBSCRIBE_BASE_URL` | Public base URL of the API used to build the links, for example `https://<host>/api/v1` |

## How it is tested

- pytest: `tests/test_routes_unsubscribe.py`, `tests/test_services_webhook_signature.py`
  for the signature helpers, plus routing cases in `tests/test_main.py`.
- behave: `features/unsubscribe.feature` (confirmation page, valid and
  invalid signatures, unknown and already unsubscribed contacts, effect on
  the contact status, a signature for another address, missing secret, the
  browser form flow, and the isolation between clients: a link only
  unsubscribes the contact of its client and a signature is rejected for
  another client).
