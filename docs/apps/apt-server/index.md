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
