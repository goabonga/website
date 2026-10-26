# apt-server

FastAPI microservice that serves a signed APT repository with per-package
access control. It is a member of the uv workspace at `apps/apt-server`; the
import package is `apt_server` and the ASGI target is `apt_server.main:app`.

The application is documented feature by feature, in the order it was built.
Each page covers what the feature does, its endpoints, its settings, its data
model and how it is tested (pytest and behave).

## Testing

```bash
uv run --package apt-server --group dev pytest apps/apt-server
uv run --package apt-server --group dev behave apps/apt-server/features
```

Every feature has pytest tests and a behave scenario file that runs in
process. The features with pages also have browser scenarios in
`features/browser/`, tagged `@browser`: they drive Chromium against the
application and a fake OpenID provider served on real sockets (see [Browser
testing](../../testing/index.md)). They run with the other scenarios, or alone:

```bash
uv run --package apt-server --group dev behave apps/apt-server/features -t @browser
```

`E2E_SKIP_BROWSER=1` skips them, and `E2E_HEADLESS=false` shows the browser.
The browser itself is installed once with `uv run playwright install chromium`.

## Features

- [Application foundation](00-foundation.md)
- [OIDC authentication](01-oidc-authentication.md)
- [Access control rules](02-access-control.md)
- [Package catalog and ACL](03-package-catalog.md)
- [APT indexes](04-apt-indexes.md)
- [APT client endpoints](05-apt-endpoints.md)
- [Package API](06-package-api.md)
- [Chunked upload](07-chunked-upload.md)
- [User cache and webhooks](08-user-cache-webhooks.md)
- [Web login sessions](09-web-sessions.md)
- [Public web pages](10-web-ui.md)
- [Package dashboard](11-dashboard.md)
