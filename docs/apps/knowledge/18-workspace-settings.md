# Workspace switching, plans and settings

A workspace is an organization (the `tenants` table). Users can belong to
several workspaces, pick the active one, manage its subscription from the
browser and rename it. The routes live in
`knowledge.routes.web.organizations` and are mounted on the internal
sub-application under `/organizations` (tag `Web`). The same router is also
mounted under `/tenants`, hidden from the OpenAPI schema, for old links. Like
every workspace page they require a signed-in user (see [Web
authentication](14-web-authentication.md)).

## Routes

| Route | Behavior |
| --- | --- |
| `POST /organizations/switch` | Makes another workspace the active one: checks that the user is a member of `organization_id` (or the legacy `tenant_id`), sets the `active_tenant_id` cookie for 30 days and redirects to `/dashboard`. An unknown or foreign workspace is ignored and also redirects to `/dashboard`. |
| `GET /organizations/pricing` | Plan comparison page. Shows the plans of the billing service (see [Billing integration](09-billing.md)), the current plan and the current billing period (monthly or yearly, deduced from the active subscription price). A billing failure is displayed on the page, and without billing no plan is invented (a message says the plans are unavailable). A plan with a custom price shows a *Contact Sales* link to `SALES_EMAIL` when it is set. Without active workspace it redirects to `/dashboard`. |
| `POST /organizations/checkout` | Creates a Stripe Checkout session through the billing client for `price_id` and redirects (`303`) to its URL. The success and cancel URLs are `BILLING_CHECKOUT_SUCCESS_URL` and `BILLING_CHECKOUT_CANCEL_URL` (see [Billing integration](09-billing.md)); they must be in the checkout allow-list of the application in billing, and the checkout is refused when they are not set. The customer name is the user's name for a personal workspace, otherwise the workspace name. |
| `GET /organizations/upgrade/preview?price_id=` | JSON proration preview of a plan change: plan names, prices, line items, subtotal, credit applied and total. Errors are returned as `{"error": ...}` (with `has_subscription: false` when the workspace has no subscription). |
| `POST /organizations/upgrade` | Upgrades the active subscription to `price_id` with proration and redirects to the pricing page with `success=true&upgraded=true` (or `error=upgrade_failed`). A workspace without subscription is sent to a checkout instead. |
| `GET /organizations/settings` | Settings page with the workspace usage (see [Usage quotas](07-quotas.md)). |
| `POST /organizations/settings` | Renames the workspace and redirects back to the settings page. |

When billing is not configured, checkout and upgrade redirect to
`/organizations/pricing?error=billing_not_configured`. A `BillingAPIError`
redirects to the pricing page with the message in the `error` parameter.

### Who can do what

The settings page and the rename require the owner or admin role of the
workspace; regular members get the `errors/403.html` page with status `403`.
Switching, pricing, checkout and upgrade are available to every member.

## Templates

`tenants/pricing.html` and `tenants/settings.html` (the template directory
keeps the historical `tenants` name), extending `base.html`.

## Navigation

For a workspace administrator (owner or admin, or a user holding the `*` scope) the sidebar
gains the *Workspace* section with *General* (the settings page) and *Billing* (the plans);
the *Billing* item is active on the plans page and *General* on the settings page. When the
user belongs to several workspaces the footer of the sidebar becomes a selector that posts to
`/tenants/switch` as soon as another workspace is chosen. The dashboard shows a *Manage* link
to the settings under the plan. Regular members see none of these.

## Tests

pytest (`test_web_organizations.py`, the part covering these routes): switching
with both parameter names and with foreign workspaces, the pricing page for
every billing outcome, checkout, upgrade preview and upgrade including errors,
and the settings page and update with admin, non-admin and missing workspace.

behave (`features/workspaces.feature`): real routes and templates, in-memory
store, fake billing client and quota service.

- Switching workspace sets the active workspace
- Switching to a workspace I do not belong to is ignored
- The pricing page compares the plans of the billing service
- The pricing page needs a workspace
- The pricing page reports a billing failure
- Choosing a plan redirects to the payment page
- Choosing a plan without billing configured goes back to pricing
- A checkout failure is shown on the pricing page
- The upgrade preview shows the proration
- The upgrade preview needs a subscription
- Upgrading an existing subscription applies the proration
- Upgrading without a subscription starts a checkout
- Administrators see the workspace settings
- Regular members cannot see the workspace settings
- Renaming the workspace
- Regular members cannot rename the workspace
- The legacy tenants prefix serves the same pages

browser (`features/workspaces.feature` in `features/browser/`, tag `@browser`): the pages in a
real Chromium, signed in through the fake OpenID provider, over a SQLite file. The billing
service is an in-memory fake that returns the plans, the subscription and the proration
quote that the scenario declares; its checkout sends the customer straight back to the
success address of the application. Every link of the pages is followed to check that it
leads to a page.

- A member of two workspaces switches from the sidebar
- A single workspace is shown without a switcher
- The billing page lists the plans and marks the current one
- A workspace without subscription is sent to the payment page
- A subscriber previews and confirms an upgrade
- The upgrade can be cancelled from the confirmation
- A billing outage is reported on the billing page
- An administrator renames the workspace
- The settings show the plan and lead to the billing page
- A regular member does not see the workspace administration
- The workspace pages only lead to pages that exist
