# Billing administration

Administration of the multi-SaaS Stripe billing platform. Operators holding
`billing:read` can browse the SaaS applications registered on the billing service with their
products, prices, customers and subscriptions; `billing:write` allows creating and editing
them. All data lives in the billing service (which talks to Stripe); this application only
renders its API. The navigation link appears for users who hold `billing:read`.

## What it adds

| Module | Role |
| --- | --- |
| `internal/services/billing_client.py` | HTTP client for billing API (billing.internal). |
| `internal/routes/billing.py` | Billing admin routes for HTML pages. |

It also ships 11 Jinja2 template(s) under `internal/templates/` (packaged with the wheel).

## Endpoints

| Method | Path | Required scope | Description |
| --- | --- | --- | --- |
| GET | /billing | `billing:read` | Billing dashboard - overview of all SaaS apps. |
| GET | /billing/saas/new | `billing:write` | New SaaS app form. |
| POST | /billing/saas/new | `billing:write` | Create a new SaaS app. |
| GET | /billing/saas/{saas_id} | `billing:read` | SaaS app detail view with products and customers. |
| GET | /billing/saas/{saas_id}/edit | `billing:write` | Edit SaaS app form. |
| POST | /billing/saas/{saas_id}/edit | `billing:write` | Update a SaaS app. |
| GET | /billing/saas/{saas_id}/products | `billing:read` | List all products for a SaaS app. |
| GET | /billing/saas/{saas_id}/products/new | `billing:write` | New product form. |
| POST | /billing/saas/{saas_id}/products/new | `billing:write` | Create a new product in Stripe with features, limits, and trial settings. |
| GET | /billing/saas/{saas_id}/products/{product_id} | `billing:read` | Product detail with prices. |
| GET | /billing/saas/{saas_id}/products/{product_id}/edit | `billing:write` | Edit product form with features and limits. |
| POST | /billing/saas/{saas_id}/products/{product_id}/edit | `billing:write` | Update a product with features, limits, and trial settings. |
| GET | /billing/saas/{saas_id}/products/{product_id}/prices/new | `billing:write` | New price form. |
| POST | /billing/saas/{saas_id}/products/{product_id}/prices/new | `billing:write` | Create a new price in Stripe. |
| POST | /billing/saas/{saas_id}/products/{product_id}/prices/{price_id}/toggle | `billing:write` | Toggle a price active/inactive status. |
| GET | /billing/saas/{saas_id}/customers | `billing:read` | List customers for a SaaS app. |
| GET | /billing/saas/{saas_id}/customers/{customer_id} | `billing:read` | Customer detail with subscriptions. |
| POST | /billing/saas/{saas_id}/customers/{customer_id}/portal | `billing:read` | Redirect to Stripe Customer Portal, coming back to `return_url` or to the first URL of the app's checkout allow-list. |
| GET | /billing/saas/{saas_id}/subscriptions | `billing:read` | List subscriptions for a SaaS app. |
| GET | /billing/saas/{saas_id}/subscriptions/{subscription_id} | `billing:read` | Subscription detail view. |
| POST | /billing/saas/{saas_id}/subscriptions/{subscription_id}/cancel | `billing:write` | Cancel a subscription, at the end of the period or immediately. |
| POST | /billing/saas/{saas_id}/subscriptions/{subscription_id}/reactivate | `billing:write` | Undo a cancellation scheduled for the end of the period. |
| POST | /billing/saas/{saas_id}/subscriptions/{subscription_id}/sync | `billing:write` | Sync a subscription from Stripe. |

All billing pages request the whole `billing` resource (`read`, `write`, `delete`) plus `billing:admin` in one
exchange. The `require_billing_admin` guard, for `billing:admin`-only pages, also asks for that scope
in the exchange (it is not one of the `read`, `write` and `delete` scopes of the resource); only the
[client binding forms](06a-billing-client-bindings.md) use it.

## Pages

- **Dashboard** (`/billing`): the list of SaaS applications.
- **SaaS application** (`/billing/saas/new`, `/billing/saas/{id}` and `/edit`): create,
  inspect (products and customers) and update an application. Administrators also manage the
  OAuth clients bound to the application there, see [SaaS client bindings](06a-billing-client-bindings.md).
- **Products and prices** (`/billing/saas/{id}/products...`): list, create and edit products
  (with feature lists, limits and trial settings that are stored as product metadata), add
  prices and toggle a price between active and inactive.
- **Customers** (`/billing/saas/{id}/customers...`): list and detail with all the customer's
  subscriptions. `POST .../portal` redirects the operator to a Stripe customer-portal session
  created by the billing service. Stripe sends the operator back to the `return_url` of the
  form or, by default, to the first entry of the SaaS app's checkout URL allow-list (see
  [Checkout URL allow-list and branding](06b-billing-checkout-urls.md)): the billing service
  refuses any other URL, so an app without allow-list has no portal and the page says so.
- **Subscriptions** (`/billing/saas/{id}/subscriptions...`): list (filtered by any billing
  status) and detail, cancel a subscription (at the end of the period, or immediately),
  reactivate one that is scheduled for cancellation, or re-synchronise it from Stripe.

The dashboard and the product lists include the inactive SaaS apps and products, so that they
can be reactivated from their edit form. A checkbox that is not ticked is not sent by the
browser: an unticked "Active" box on an edit form deactivates the record. The forms of new
prices leave the currency and the interval empty by default and the billing service applies its
own (`DEFAULT_CURRENCY`, `DEFAULT_RECURRING_INTERVAL`). The limits of a product are free-form
named whole numbers: the names are those the SaaS app reads from its plan.

Every action redirects back with a `success` or `error` query parameter that the
templates show as a banner.

## Billing client

`internal.services.billing_client.BillingClient` (instance `billing_client`) uses the OAuth2
client-credentials grant and caches one token per scope set. The billing service partitions its
API between SaaS apps: a client only sees the apps it is bound to, and only a token that carries
the admin scope (`PARTITION_ADMIN_SCOPE` on the billing side) may list every app, create one or
manage bindings. The client therefore asks for:

| Call | Scopes requested |
| --- | --- |
| Reads | `BILLING_READ_SCOPE` + `BILLING_ADMIN_SCOPE` |
| Writes | `BILLING_WRITE_SCOPE` + `BILLING_ADMIN_SCOPE` |
| Creating a SaaS app | `BILLING_ADMIN_SCOPE` |

The OAuth client of this application must hold these scopes at the identity provider; an empty
`BILLING_ADMIN_SCOPE` makes the application act as an ordinary bound client. When
`BILLING_SOCKET_PATH` is set, requests travel over that Unix socket instead of TCP (the base URL
is then only a placeholder). Methods return Pydantic models; failures are logged and produce `None`,
`False` or an empty list.

## Settings

Read from environment variables (or a `.env` file) by `internal.config.Settings`.

| Variable | Default | Notes |
| --- | --- | --- |
| `BILLING_API_URL` | empty | Billing API over TCP (no default: unset, billing calls fail and the pages report an error) |
| `BILLING_SOCKET_PATH` | empty | Unix socket path (for example the billing service's runtime socket); takes precedence over the URL |
| `BILLING_READ_SCOPE` | `billing:platform:read` | Scope of read calls |
| `BILLING_WRITE_SCOPE` | `billing:platform:write` | Scope of write calls |
| `BILLING_ADMIN_SCOPE` | `billing:admin` | Admin scope, to set to the billing service's `PARTITION_ADMIN_SCOPE` |
| `BILLING_TIMEOUT` | `30.0` | Seconds allowed per request |
| `BILLING_PAGE_SIZE` | `20` | Rows per page of the customer and subscription lists (the next page is offered when a full page came back) |
| `BILLING_RECENT_LIMIT` | `10` | Rows of the recent customers and subscriptions of a SaaS app page |

## Tests

pytest:

- `tests/routes/test_billing.py`
- `tests/services/test_billing_client.py`
- `tests/routes/test_billing_sidebar.py`

The tests cover every route handler (success, not-found and error redirects), the billing client (scopes taken from the settings, token caching per scope set, socket transport, every endpoint wrapper), the templates rendered for real (no preset limit names, reactivation button) and the settings defaults. The customer and subscription lists are tested for the page size they hand to their template.

`tests/routes/test_billing_sidebar.py` opens every page of this feature through the application with its real templates (throw-away SQLite database, mocked service clients) and, for each scope combination, checks the sidebar: exactly the links the scopes permit, a single active link and the signed-in user.

Behave scenarios, run in-process with `uv run --package internal behave apps/internal/features` (`features/billing.feature`):

- View billing dashboard
- The dashboard lists inactive SaaS apps too
- View billing dashboard unauthenticated
- View new SaaS app form
- Create a new SaaS app successfully
- Create a new SaaS app failure
- View SaaS app detail
- View SaaS app detail not found
- View SaaS app edit form
- View SaaS app edit form not found
- Update a SaaS app successfully
- An unticked Active box deactivates the SaaS app
- A ticked Active box keeps the SaaS app active
- Update a SaaS app failure
- List products for a SaaS app
- List products when SaaS app not found
- View new product form
- View new product form when SaaS not found
- Create a product successfully
- Create a product failure
- View product detail
- View product detail when SaaS not found
- View product detail when product not found
- View product edit form
- Update a product successfully
- Update a product failure
- View new price form
- View new price form when resource not found
- Create a price successfully
- Create a price and leave the currency and interval to the billing service
- Create a price failure
- Toggle price active status
- Toggle price when price not found
- List customers for a SaaS app
- List customers when SaaS not found
- View customer detail
- View customer detail when SaaS not found
- View customer detail when customer not found
- Redirect to customer portal
- Customer portal needs a return URL the SaaS app accepts
- Customer portal redirect failure
- List subscriptions for a SaaS app
- List subscriptions when SaaS not found
- View subscription detail
- View subscription detail when SaaS not found
- View subscription detail when subscription not found
- Cancel subscription successfully
- Cancel subscription failure
- Reactivate subscription successfully
- Reactivate subscription failure
- Sync subscription successfully
- Sync subscription failure
- Sidebar on the billing dashboard
- Sidebar on the new SaaS app form
- Sidebar on the SaaS app detail
- Sidebar on the SaaS app edit form
- Sidebar on the products list
- Sidebar on the new product form
- Sidebar on the product detail
- Sidebar on the product edit form
- Sidebar on the new price form
- Sidebar on the customers list
- Sidebar on the customer detail
- Sidebar on the subscriptions list
- Sidebar on the subscription detail
- Sidebar gated links follow the scopes on the billing dashboard

The billing client is replaced by an `AsyncMock`; scenarios exercise each page with authorized, unauthorized and unauthenticated users and the redirects of every mutation.

Browser scenarios, run in Chromium against the application served on a local socket (`features/browser/billing.feature`, `uv run --package internal --group dev behave apps/internal/features -t @browser`):

- The dashboard lists the SaaS apps
- Only the holders of the billing scope see the Billing link
- The Billing link leads to the dashboard
- A user without the billing scope gets the access denied page
- A user who may only read cannot create a SaaS app
- An anonymous visitor comes back to the page asked for after the login
- A SaaS app is created from the form
- A SaaS app the billing service refuses is reported on the form
- The form requires a name and a slug
- The detail of a SaaS app links to its products, customers and subscriptions
- A SaaS app that does not exist sends the user back to the dashboard
- A SaaS app is updated from its edit form
- Unticking Active deactivates the SaaS app
- A failed update is reported on the form
- The products of a SaaS app are listed
- A product is created with a feature
- A product the billing service refuses is reported on the form
- A product is updated from its edit form
- A product that does not exist sends the user back to the list
- A price is created for a product
- A price the billing service refuses is reported
- A price is toggled from the product page
- The customers of a SaaS app are listed with their detail
- The next page of customers is offered when a page is full
- There is no next page when the last page is not full
- A customer that does not exist sends the user back to the list
- The Stripe portal of a customer is opened
- The portal needs a return URL the SaaS app accepts
- A portal the billing service cannot open is reported
- The subscriptions are listed and filtered by status
- The detail of a subscription shows its customer
- A subscription that does not exist sends the user back to the list
- A subscription is canceled at the end of the period
- A subscription that cannot be canceled is reported
- A subscription is synchronized from Stripe
- A subscription that cannot be synchronized is reported

The scenarios walk through the SaaS apps, products, prices, customers and subscriptions: forms are filled and submitted, the flash messages of success and failure are read, the feature rows of the product form are added by its JavaScript, the Stripe portal redirect is followed to a stub page (the browser never leaves the local servers), and the pagination offers a next page exactly when a full page of `BILLING_PAGE_SIZE` rows came back.
