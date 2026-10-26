# Checkout URL allow-list and branding

Two settings of a SaaS app decide what its customers see when they leave for Stripe, and are
now edited on the SaaS app form (`/billing/saas/new` and `/billing/saas/{saas_id}/edit`) and shown
on its page. They belong to the billing service, see its
[SaaS applications](../billing/05-saas-apps.md) page.

## Checkout URL allow-list

Stripe sends the customer back to a URL chosen by the caller once a Checkout or a customer-portal
session ends. The billing service only accepts a URL that starts with one of the prefixes of the
app's allow-list, and, unless `REDIRECT_ALLOWLIST_REQUIRED=false`, refuses every URL when the app
has none. Without an allow-list an app can neither create checkout sessions nor open the customer
portal from the [customer page](06-billing.md#pages), so set one when you create the app.

In the form it is a text area with **one URL prefix per line**: an absolute `http` or `https` URL,
an origin optionally followed by a path (`https://app.example.test`,
`https://app.example.test/billing`), without credentials, query string or fragment. Blank lines
and duplicates are dropped. The application checks these rules before calling the billing
service, which remains the authority and answers with its own refusal if it disagrees. An empty
text area **clears** the allow-list.

The customer portal button uses the first prefix as the page Stripe returns the operator to.

## Branding

Free-form JSON stored with the app. The checkout reads `locale` (the language of the Stripe
Checkout page) and `custom_text` (the Stripe `custom_text` block); other keys are kept but not
interpreted. In the form it is a JSON text area; the text must be a JSON object, anything else is
refused with an explanation. An empty text area clears the branding.

## Behaviour

- Creating an app sends the fields that are filled; updating always sends both, so that emptying
  a field removes the value (`null` on the API). The other fields of the form keep their former
  meaning (an empty webhook URL, for example, leaves it unchanged).
- A refusal returns to the form with the reason in the error banner, and nothing is sent.
- The SaaS app page shows both settings: the prefixes, or a note that checkout and portal
  redirects are refused, and the branding as indented JSON.

## Billing client

`create_saas_app` and `update_saas_app` take `branding` and `checkout_url_allowlist`. On update
an argument that is left out is not sent (`internal.services.billing_client.UNSET`), and `None`
is sent as `null` to clear the field. `SaasApp` exposes both fields.

## Settings

No new variable. The behaviour on an empty allow-list is the billing service's
`REDIRECT_ALLOWLIST_REQUIRED`.

## Tests

pytest:

- `tests/services/test_billing_client.py`
- `tests/routes/test_billing.py`
- `tests/routes/test_billing_sidebar.py` (the form and detail pages are rendered with the new fields for every scope combination)

They cover the two parsers (separators, duplicates, every refused shape), the create and update
routes (parsed fields passed on, invalid input refused before the service is called, empty fields
clearing) and the form and page templates.

Behave scenarios (`features/billing_checkout_urls.feature`):

- The new SaaS app form offers the allow-list and the branding
- Create a SaaS app with a checkout URL allow-list and a branding
- A checkout URL without scheme is refused
- A checkout URL with a query string is refused
- A branding that is not a JSON object is refused
- The edit form shows the current allow-list and branding
- Emptying the fields on the edit form clears them
- The SaaS app page shows the allow-list and the branding
- The SaaS app page says when redirects are refused

The billing client is replaced by an `AsyncMock`: what the billing service really accepts was not
checked against a running instance.

Browser scenarios, run in Chromium against the application served on a local socket (`features/browser/billing_checkout_urls.feature`, `uv run --package internal --group dev behave apps/internal/features -t @browser`):

- The new SaaS app form offers the allow-list and the branding
- A SaaS app is created with a checkout URL allow-list and a branding
- Several checkout URLs are given one per line
- A checkout URL without scheme is refused and the user stays on the form
- A checkout URL with a query string is refused on the edit form
- A branding that is not a JSON object is refused
- The edit form shows the current allow-list and branding
- Emptying the fields on the edit form clears them
- The page of the SaaS app shows the allow-list and the branding
- The page of the SaaS app says when redirects are refused

The allow-list is typed one URL per line in the form. The Stripe portal button now needs a return URL the SaaS app accepts, which the browser scenarios of the billing page follow.
