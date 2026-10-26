# apt-server

FastAPI microservice that serves a signed APT repository with per-package
access control. It is a member of the uv workspace at `apps/apt-server`; the
import package is `apt_server` and the ASGI target is `apt_server.main:app`.

The application is documented feature by feature, in the order it was built.
Each page covers what the feature does, its endpoints, its settings, its data
model and how it is tested (pytest and behave).

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
