# Web client

The website itself is a single page application written in TypeScript and
bundled with Vite. Its sources live in `apps/frontend/web/`; the Python server
only has to serve the page it produces. This feature adds the sources, the
build, and the generator that turns the built page into a server template.

## Layout

| Path | Role |
|------|------|
| `web/index.html` | Development page: contains the default values of the runtime configuration and the page shell |
| `web/src/main.ts`, `router.ts` | Entry point and a small client-side router with protected routes |
| `web/src/auth/` | OAuth2 authorization code flow with PKCE (token storage, refresh, user info) |
| `web/src/api/` | Server-sent events client used by the chat box |
| `web/src/analytics/` | Browser analytics SDK posting events to the analytics service |
| `web/src/components/`, `pages/` | Chat box, user menu, home, login, callback and error pages |
| `web/src/config.ts` | Reads the `window.APP_CONFIG` object injected in the page |
| `web/scripts/generate-template.js` | Template generator (see below) |
| `web/vite.config.ts` | Vite configuration |

## Build

Node.js 18 or later is needed (deployments install Node.js 20).

```bash
npm --prefix apps/frontend/web ci
npm --prefix apps/frontend/web run build
```

`npm run build` runs, in order:

1. `tsc`: type-check the sources.
2. `vite build`: bundle into `apps/frontend/web/dist` (`index.html` and
   `assets/index.js`, `assets/index.css`). In production mode the asset URLs
   are prefixed with `/static/`.
3. `node scripts/generate-template.js`: build the template.

`npm run build:template` runs the last step alone. `npm run dev` starts the
Vite development server on port 3000, proxying `/api` and `/oauth2` to the
upstream services configured in `vite.config.ts`.

## The template generator

`dist/index.html` still contains the development values (application name,
URLs, public client id, legal notice, welcome words, social links). The
generator applies an ordered list of regular-expression replacements that swap
each of them for a Jinja2 variable, for example `appName: "..."` becomes
`appName: {{ app_name | tojson }}`, and rewrites the animated welcome words
into a Jinja2 loop. The values of the JavaScript configuration go through the
`tojson` filter, so that the web client reads them unchanged whatever they
contain (an apostrophe, an `&`, a closing script tag); plain HTML escaping
would leave entities such as `&#39;` in the strings. The visible text of the
page keeps the default HTML escaping. It writes the result to
`apps/frontend/src/frontend/templates/index.html`, creating the directory when
needed, and exits with an error asking to run the build first when
`dist/index.html` is missing.

The generated template is committed: the Python server works without Node.js
and the build is only needed after changing the web client or to produce the
`/static` assets. Building from the committed sources reproduces the committed
template byte for byte.

The template contains none of the development values; its variables are meant
to be filled by the server when it renders the page.

## Ignored files

`apps/frontend/.gitignore` excludes `web/node_modules/` and `web/dist/`.

## Tests

pytest (`tests/test_web_client.py`):

- the web client files exist;
- the build script chains `tsc`, `vite build` and the generator;
- Vite prefixes assets with `/static/` in production;
- the generator's target is the template inside the Python package;
- the committed template uses every expected variable and contains none of the
  development values;
- the generator, run with Node.js on a sample page in a temporary directory,
  replaces the hard-coded values, and fails when there is no build (these two
  tests are skipped when `node` is not installed).

behave (`features/web_client.feature`, steps in
`features/steps/web_client_steps.py`):

- The web client sources are part of the application
- The build script type-checks, bundles and generates the template
- The committed template is parametrised by the server settings
- The generator turns a built page into a template
- The generator refuses to run without a build

The last two scenarios need Node.js and are skipped without it. The full
`npm ci` and `npm run build` need network access: they are run by the browser
scenarios of [SPA serving](04-spa-serving.md), which build the web client and
open it in a browser.
