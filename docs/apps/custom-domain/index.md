# custom-domain

Centralized service for managing custom domains of multi-tenant applications.
It registers a customer domain, verifies its DNS CNAME record, provisions a
Let's Encrypt certificate through certbot and writes the nginx virtual host
that proxies the domain to the right upstream.

The application is a FastAPI service (`custom_domain.main:app`) with Celery
workers for the long-running steps. This section documents it feature by
feature, in the order the features were built; each page describes what the
feature adds, its settings and how it is tested.

## Features

| Page | Feature |
| --- | --- |
| [Application foundation](00-foundation.md) | Settings, logging, database session, health check |
| [OAuth2 authentication](01-oauth2-authentication.md) | Bearer token validation and scope checks |
| [Data model](02-data-model.md) | Models, status enum, initial alembic migration |
| [Nginx configuration rendering](03-nginx-rendering.md) | Jinja2 templates and nginx file management |
| [SSL provisioning](04-ssl-provisioning.md) | Certbot, Celery application, provisioning tasks |
| [DNS verification](05-dns-verification.md) | CNAME check task and periodic scan |
| [Nginx template administration](06-template-admin.md) | Admin API for nginx templates |
| [Authorized client administration](07-client-admin.md) | Admin API for authorized clients |
| [Domain API](08-domain-api.md) | Register, inspect, update, delete, verify and provision domains |
| [Provisioning status and events](09-provisioning-events.md) | Status snapshot, SSE stream and event history |
| [Domain maintenance](10-domain-maintenance.md) | Certificate renewal, health checks, cleanup and purge |
| [Administration statistics](11-admin-stats.md) | Overview, top clients, recent activity and dashboard |
| [Command line interface](12-cli.md) | Seed, client and template commands |
| [Python client SDK](13-python-sdk.md) | Typed sync and async client for the API |
| [TCP upstream targets](14-upstream-targets.md) | Host and port upstreams next to Unix sockets, strict validation |
| [Per-client template ownership](15-template-ownership.md) | Shared and client-owned nginx templates |
| [Client status webhooks](16-webhooks.md) | Signed callbacks on status changes, SDK verification helper |
