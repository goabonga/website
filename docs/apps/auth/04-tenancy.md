# Multi-tenancy and OIDC discovery

Every request is attributed to a tenant (an organisation): the platform
tenant on the main domain, or a customer organisation reached through a
subdomain, a path prefix or its own domain. This feature adds the tenant
resolution middleware, the services that own tenants, their roles, branding
and trust policies, the issuer computation and the OpenID Connect discovery
document.

## What it does

### Tenant resolution

`auth.middlewares.tenant.TenantMiddleware` is an ASGI middleware that
resolves the tenant of each HTTP request, in this order:

1. Path prefix: `/t/{slug}/...`. The prefix is stripped from the path the
   application sees.
2. Subdomain: `{slug}.{TENANT_BASE_DOMAIN}`.
3. Custom domain (a CNAME pointing at the service), when
   `TENANT_CUSTOM_DOMAIN_LOOKUP` is enabled.
4. Fallback to the platform tenant (the main domain).

The result is a `TenantContext` (`tenant_id`, `tenant_slug`,
`resolution_method`) stored in `scope["tenant"]` and in a context variable
(`get_tenant_context`, `require_tenant`). A subdomain of the base domain that
matches no tenant is redirected (302) to the same path on the base domain.
`auth.main` installs the middleware only when `TENANT_BASE_DOMAIN` is set.

The module also derives tenant-scoped cookie names and domain:
`get_session_cookie_name()` returns `session_{slug}` for subdomain and path
resolution (the plain cookie name otherwise), `get_csrf_cookie_name()`
returns `csrf_{slug}` and `get_session_cookie_domain()` returns
`.{TENANT_BASE_DOMAIN}` so that the cookie is shared between
`slug.base-domain` and `base-domain/t/slug/`.

### Tenant services

- `TenantService` (`tenant_service`): lookups by id, slug and active custom
  domain, the platform tenant, members, identity provider records, branding
  and template rows, and `create_organisation_with_owner`, which creates a
  tenant, seeds its default roles and enrols the caller as owner.
- `TenantRoleService` (`tenant_role_service`): the per-tenant roles. New
  tenants get the system roles `owner`, `admin` and `member` (`member` is
  the default role of new registrants). Custom roles carry a list of scopes
  validated against the scopes the tenant is allowed to grant. System roles
  cannot be deleted.
- `TrustPolicyService`: decides whether a user may sign in to a tenant
  according to its trust mode, see the table below.
- `BrandingService` and `BrandingConfig`: per-tenant colors, logos, fonts,
  custom CSS/JS and template overrides. `BrandingConfig.from_tenant(None)`
  gives the platform defaults and `to_css_variables()` renders them as CSS
  custom properties. `TenantTemplateLoader` lets a tenant override the
  customizable page and e-mail templates.
- Repositories for tenants, tenant roles, trust, branding and issuer
  lookups under `auth.db.repositories`.

| Trust mode | Who may sign in |
| --- | --- |
| `none` | Users registered on the tenant, and its members |
| `members_only` | Members of the tenant only |
| `all` | Any authenticated user |
| `specific` | Users registered on one of the trusted tenants, and members |

### Issuer and discovery

`auth.services.issuer.get_tenant_issuer` derives the issuer URL from trusted
configuration, never from the `Host` header: the active custom domain, else
`https://{slug}.{TENANT_BASE_DOMAIN}`, else `https://{TENANT_BASE_DOMAIN}`
for the platform tenant, else `ISSUER`.

`GET /.well-known/openid-configuration` returns the OpenID Connect
Discovery document for the current tenant. It already advertises the
authorization, token, userinfo, revocation, introspection, device
authorization, pushed authorization request and registration endpoints under
the issuer; those endpoints are implemented by the features that follow.

## Endpoints

| Method | Path | Handler | Summary |
| --- | --- | --- | --- |
| GET | `/.well-known/openid-configuration` | `openid_configuration` | Return the OpenID Connect Discovery metadata document. |

## Settings

| Variable | Default | Description |
| --- | --- | --- |
| `ISSUER` | unset | Auto-detected from request if not set |
| `SESSION_COOKIE_NAME` | `session` | Session cookie name |
| `TENANT_BASE_DOMAIN` | (empty) | Base domain for tenant subdomains (e.g., "auth.example.com") |
| `TENANT_CUSTOM_DOMAIN_LOOKUP` | `True` | Enable custom domain (CNAME) lookup |

## Data model

Uses the tenant tables created by the data model feature (`tenants`,
`tenant_members`, `tenant_roles`, `tenant_branding`, `tenant_templates`,
`tenant_trusted_sources`, `identity_providers`). The platform tenant is the
one tenant flagged `is_platform`; it is a row like the others, no migration
inserts it. The webhook tables are used by the next feature.

## Tests

- pytest: 12 new test modules and 3 existing modules extended.
  New modules: `tests/test_branding_repository.py`, `tests/test_branding_service.py`, `tests/test_issuer_repository.py`, `tests/test_issuer_service.py`, `tests/test_middleware_tenant.py`, `tests/test_routes_discovery.py`, `tests/test_tenant_repository.py`, `tests/test_tenant_role_repository.py`, `tests/test_tenant_role_service.py`, `tests/test_tenant_service.py`, `tests/test_trust_repository.py`, `tests/test_trust_service.py`.
  Extended: `tests/test_api_deps.py`, `tests/test_main.py`, `tests/test_routes_health.py`.
- behave: `features/tenancy.feature` with the scenarios *The platform publishes its OpenID Connect discovery document*, *The issuer follows the tenant*, *A tenant is resolved from its subdomain*, *A tenant is resolved from a path prefix*, *A tenant is resolved from its custom domain*, *The main domain falls back to the platform tenant*, *An unknown subdomain is redirected to the main domain*, *Cookie names are scoped to the tenant*, *Creating an organisation seeds its roles and enrols the owner*, *Trust policies decide who may sign in to a tenant*, *Branding falls back to the platform defaults*.

The behave scenarios run the middleware around a tiny ASGI application and
replace its database lookups with in-memory answers; the trust policy is
evaluated with a fake repository.
