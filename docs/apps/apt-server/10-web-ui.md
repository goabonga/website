# Public web pages

Server-rendered pages (Jinja2) for people: browse the packages they may see,
learn how to configure `apt`, and open a package. They are hidden from the
OpenAPI schema and share the layout `templates/base.html`.

## Pages

| Page | Description |
| --- | --- |
| `GET /` | Package list with filters `suite`, `component` and `q` (name search, case insensitive), 25 rows per page (`page`, values above the last page are clamped, `page < 1` answers 422) |
| `GET /setup` | Setup guide with the commands to install the signing key and add the source |
| `GET /packages/{package_id}` | Detail page of one package |

The caller is resolved like for apt clients (header credentials or the session
cookie), so the pages adapt to who is looking:

- the list only contains packages the caller can read (the same visibility
  filter as the indexes), and the component filter only offers public
  components to visitors;
- a "Sign in" button and a notice appear for anonymous visitors when
  `OAUTH2_ISSUER` is set, and a signed-in user sees their name, avatar and a
  "Logout" link in the sidebar;
- the setup guide always shows the public repository (key from `/pubkey.gpg`,
  keyring named after the host, first suite and first public component), and
  adds the private repository guide (personal access token, `auth.conf.d`
  credentials, verification with `curl`) for signed-in users. The token page
  link is built from the issuer;
- the detail page answers 404 when the package does not exist or the caller
  cannot read it, and shows the owner through the user cache (the email when
  known, the raw identifier otherwise).

The sidebar of the layout is a navigation landmark (`<nav aria-label="Main">`),
so that assistive technologies and browser tests can find the menu.

Templates live in `src/apt_server/templates/` (`base.html`, `index.html`,
`setup.html`, `package_detail.html`, `partials/pagination.html`) and are
included in the wheel.

## Settings

The pages use `APP_NAME` (title), `APT_SUITES`, `APT_COMPONENTS`,
`APT_PUBLIC_COMPONENTS` and `OAUTH2_ISSUER`; no new variable is introduced.

## Dependencies

`jinja2` is added by this feature.

## Tests

- pytest: `tests/test_web_pages.py` (visitor and owner views, sign-in links,
  filters, component options, empty state, pagination, setup page for
  visitors and signed-in users, detail page visibility, shared packages,
  invalid identifiers) against SQLite.
- behave: `features/web_ui.feature` with the scenarios "The home page lists
  public packages", "The package list can be searched", "The setup page
  explains how to register the repository", "A public package has a detail
  page", "A private package detail page is hidden from visitors" and "Owners
  see their private packages on the home page".
- browser: `features/browser/web_ui.feature` renders the pages in Chromium
  with the browser console watched: "The home page lists the public packages
  to a visitor", "The package list can be filtered by name", "The package list
  is paginated", "The setup guide explains how to register the repository", "A
  public package has a detail page", "A private package is hidden from
  visitors", "A visitor signs in from the home page", "A signed-in user sees
  the private repository guide and the owner" and "Signing out brings the
  sign-in button back". Avatars hosted by third parties are answered with a
  pixel and any other request to a third party fails the scenario.
