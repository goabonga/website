# Plan slug and free-form limits

A product of the billing service is a plan of a SaaS app. Two things identify and describe it to
the application that sells it: its **slug**, and the **limits** the application reads from its
plan. This feature gives both a proper place on the product forms
(`/billing/saas/{saas_id}/products/new` and `.../products/{product_id}/edit`).

## Slug

The billing service stores the slug of a product in its own column, unique within a SaaS app
(two apps can both have a `pro` plan), and mirrors it in the metadata. The form field **Plan Slug**
now sends it as the `slug` field of the API instead of a metadata key:

- on creation, an empty slug lets the billing service derive it from the name;
- on edition, an empty field leaves the slug as it is, and the field shows the slug of the product
  itself;
- a slug is at most 100 lowercase letters, digits and single hyphens
  (`pro`, `team-2024`). The browser checks the pattern; the route checks it again and returns to
  the form with the reason, without calling the billing service;
- a slug already used by another product of the app is refused by the billing service (`409`)
  and the form reports that the product could not be saved.

The slug is shown in the product list and on the product page.

## Limits

The limits of a plan are named whole numbers, for example `{"seats": 5}`. The names are
whatever the SaaS app reads from `GET /plans/{app_slug}`: neither the form nor the page knows
any of them (the former list of preset names and the conventions for `-1` or for names ending
in `_bytes` are gone, the page prints the number with thousands separators).

- The editor has one row per limit (name and value) and an "Add Limit" button. The browser
  refuses a value that is not a whole number; the route does too, because the billing service
  silently drops every limit that is not an integer (text, `null`, decimals, booleans) and the
  operator would lose it without notice. A limit needs a name (spaces around it are removed).
- Whether a limit means "unlimited" at some value is a convention between the app and its plan,
  not something this application interprets.

## Metadata kept on edition

The form only knows a few keys of the product metadata: `sort_order`, `default_trial_days`,
`is_recommended`, `features` and `limits`. Saving a product now starts from its current
metadata and overwrites those keys, so that any other key an operator or another tool stored
there survives. (It used to replace the whole document.) The trial period is no longer capped
in the form: the billing service owns the maximum (`MAX_TRIAL_PERIOD_DAYS`).

## Billing client

`BillingProduct` exposes `slug`; `create_product` and `update_product` take `slug` and leave it
out of the request when it is `None`.

## Settings

No new variable.

## Tests

pytest:

- `tests/services/test_billing_client.py`
- `tests/routes/test_billing.py`
- `tests/routes/test_billing_sidebar.py` (the product pages are rendered with a slug for every scope combination)

They cover the two parsers (every accepted and refused slug and limit), the create and update
routes (slug sent apart from the metadata, unknown metadata kept, invalid input refused before the
service is called, unknown product) and the product templates rendered for real.

Behave scenarios (`features/billing_plans.feature`):

- The product form has no preset limit names
- The product form checks the shape of the slug
- The slug is sent as its own field
- Without a slug the billing service derives it from the name
- A slug with capitals or spaces is refused
- A limit that is not a whole number is refused
- Editing a product sends its new slug and keeps the metadata the form does not know
- A limit without a name is refused when editing
- The product list shows the slug of each plan
- The product page shows its limits as they are

The billing client is replaced by an `AsyncMock`; the behaviour of the billing service (slug
uniqueness, dropping of non-integer limits) is the one documented by its own pages and was not
exercised against a running instance.

Browser scenarios, run in Chromium against the application served on a local socket (`features/browser/billing_plans.feature`, `uv run --package internal --group dev behave apps/internal/features -t @browser`):

- The product form has no preset limit names
- A product is created with a slug and free-form limits
- Without a slug the billing service derives it from the name
- A slug with capitals or spaces is stopped by the form
- A limit with decimals is stopped by the form
- A limit that is not written as a whole number is refused with an alert
- A limit can be removed before the form is sent
- The edit form shows the slug and the limits of the product
- Editing a product sends its new slug and limits
- The product list shows the slug of each plan
- The product page shows its limits as they are

The limit rows are built by the JavaScript of the product form: names are free, the slug pattern and the whole number check are enforced by the browser before the form is sent, and a value such as `1e3` that passes the browser's own check is refused by the form's alert.
