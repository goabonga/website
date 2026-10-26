# Landing, dashboard and download pages

These are the first pages of the web application: the public pages that
present the product and a dashboard that summarizes the active workspace. They
are served by the internal sub-application (tag `Web`, listed in
`/internal/docs`) and rendered with Jinja2 on top of the shared
`base.html` layout.

## Public pages

| Route | Page |
| --- | --- |
| `GET /` | Landing page. A visitor who carries an `access_token` cookie is redirected to `/dashboard` (the cookie is not validated here). |
| `GET /pricing` | Plans and prices fetched from the billing service (see [Billing integration](09-billing.md)). When billing is not configured the page shows a message instead of plans (no price or limit is written in the page) and the comparison table lists the limits that the plans declare in billing, whatever their names (`-1` is shown as unlimited, `*_bytes` limits as sizes); a plan with a custom price links to `SALES_EMAIL` when it is set; a billing error is shown on the page instead of failing the request. |
| `GET /legal`, `GET /privacy`, `GET /terms` | Legal notice, privacy policy and terms of service. The operator and the contact addresses are `OPERATOR_NAME`, `CONTACT_EMAIL`, `LEGAL_EMAIL` and `PRIVACY_EMAIL`; what is empty is left out. |
| `GET /mcp`, `GET /mcp/downloads` | Download page of the Knowledge MCP: the latest published release with one card per platform (size and a link to the download API) and a selector for the older versions, built from the releases described in [MCP releases](11-releases.md). |

Their header follows the session: a visitor sees *Sign In* and *Get Started*, a
visitor who carries an `access_token` cookie sees a *Dashboard* link instead. The
*API Docs* links only appear when `DOCS_ENABLED` is true (the documentation is served
only then). The sidebar of the signed-in pages gains the *Dashboard* link.

## Dashboard

`GET /dashboard` requires a signed-in user: without a valid session cookie it
redirects to `/auth/login?redirect=<path>` (see [Web
authentication](14-web-authentication.md)). For the active workspace it shows:

- the number of collections and documents;
- the five most recently updated collections;
- the plan and the usage against the plan limits (collections, documents,
  storage), with progress bars styled as a warning above 70 percent and as
  critical above 90 percent, computed by the [quota service](07-quotas.md);
- the name of the active workspace, in the sidebar.

A user who has no workspace still gets the page, with an invitation to create
one.

The dashboard counts collections through the legacy workspace link
(`collections.tenant_id`), so a workspace shows the collections it owns as an
organization; personal collections are listed by the API instead.

## Settings

The pages carry no value of the deployment. The operator of the service is configured, and
what is empty is left out of the pages (no address, no `mailto:` link):

| Variable | Default | Description |
| --- | --- | --- |
| `OPERATOR_NAME` | empty | Who publishes the service (legal notice). |
| `CONTACT_EMAIL` | empty | General contact address (legal notice). |
| `SALES_EMAIL` | empty | Address of the *Contact Sales* link of the plans with a custom price. |
| `LEGAL_EMAIL` | empty | Address of the legal notice and the terms of service. |
| `PRIVACY_EMAIL` | empty | Address of the privacy policy. |
| `APP_BASE_URL` | empty | Public URL, shown in the MCP configuration example of the download page. |

`knowledge.templating.create_templates()` builds the template engine of the web routers: it
gives the templates `site()` (these settings) and the display helpers of the limits.

## Tests

pytest:

- `test_web_home.py`: the landing redirect, the legal pages, the pricing page
  with and without billing and with billing errors, and the dashboard with and
  without a workspace.
- `unit/test_templating.py`: the limit helpers, the settings given to the pages, the comparison
  table built from the limits of the plans, the absence of invented plans and of built-in
  addresses on the pricing and legal pages, the header of the public pages for a visitor and
  for a signed-in user, and the documentation link that follows `DOCS_ENABLED`.
- `test_web_downloads.py`: the download page with several releases, without any
  release and on both routes.

behave (`features/web_dashboard.feature`): templates and routes are real, the
signed-in user is injected, the billing and quota services are fakes and the
releases come from the in-memory store.

- Visitors see the landing page
- Signed-in users are sent to their dashboard
- Legal pages are public (outline: legal notice, privacy policy, terms)
- The pricing page lists the plans of the billing service
- The pricing page reports a billing failure
- The dashboard requires a signed-in user
- The dashboard shows the usage of the workspace
- A user without workspace is invited to create one
- The download page lists the published releases
- The download page works without any release

browser (`features/browser/web_dashboard.feature`, tag `@browser`): the public pages and the
dashboard in a real Chromium, served on a local port with the fake OpenID provider for
the sign-in and a SQLite file for the database. The billing service is an in-memory fake;
the binary of a release is "downloaded" from a page of the application itself. Every link
of the public pages and of the sidebar is followed to check that it leads to a page.

- A visitor discovers the product and goes on to sign up
- The landing page leads to the sign-in page and the legal pages
- Signed-in users are sent to their dashboard
- The public pages know that the visitor is signed in
- Every public page links back to the landing page
- The pricing page lists the plans of the billing service
- The pricing page tells when the plans cannot be loaded
- The dashboard requires a signed-in user
- The dashboard shows the usage of the workspace
- The MCP download page tells when there is no release
- The MCP download page offers the binaries of the latest release
- Signing in through the identity provider lands on the dashboard
- A new user lands on the dashboard of the workspace they named
- Signing out leads back to the landing page
- The pages before the sign-in only lead to pages that exist
- The public pages only lead to pages that exist
- The sidebar of the dashboard only lists the pages that exist
