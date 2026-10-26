# Multi-tenant resolution

A tenant is an organization (stored in the `tenants` table, see the [data
model](01-data-model.md)). This feature attributes each incoming request to a
tenant from its address, and provides the tenant service and schemas.

## Tenant middleware

`knowledge.middleware.tenant.TenantMiddleware` is a pure ASGI middleware. It
is installed on the public application only when `TENANT_BASE_DOMAIN` is set.
For every HTTP request it tries, in order:

1. **Path prefix**: `/t/{slug}/...`. The prefix is stripped from the path
   before routing (`/t/acme/api/v1/ping` is routed as `/api/v1/ping`) and the
   slug is looked up in the database.
2. **Subdomain**: `{slug}.<TENANT_BASE_DOMAIN>`. The subdomain must be a valid
   slug (lowercase letters, digits and dashes, 1 to 63 characters, not starting
   or ending with a dash), otherwise it is ignored.
3. **Custom domain**: when `TENANT_CUSTOM_DOMAIN_LOOKUP` is true and the host is
   neither the base domain nor a subdomain of it, the host is matched against
   `custom_domain` of active organizations whose domain status is `active` (see
   the custom domains feature).
4. Otherwise no tenant is attached (main domain).

Lookups only consider active organizations. A subdomain that does not match
any tenant is redirected with `302` to `https://<base domain><path>` (query
string preserved). Lookup errors are logged and treated as "not found".

The result is a `TenantContext(tenant_id, tenant_slug, resolution_method)`
(`path`, `subdomain` or `custom_domain`), stored in `scope["tenant"]` and in a
context variable read with `get_tenant_context()`; `require_tenant()` raises
`ValueError` when no tenant is set. The context variable is cleared when the
request ends.

## Tenant service and schemas

`TenantService` offers `create` (new tenants start on the `free` plan with empty
settings), `get_by_id`, `get_by_slug`, `list`, `update_plan` and `deactivate`.
`TenantCreate` validates `name` (1-255 characters) and `slug` (1-100 characters,
lowercase letters, digits and dashes); `TenantResponse` exposes `id`, `name`,
`slug`, `plan`, `is_active` and the timestamps.

The original repository also shipped a `scripts/create_tenant.py` helper. It
imports modules that no longer exist (an API key service and schema), so it was
not carried over.

## Settings

| Variable | Default | Description |
| --- | --- | --- |
| `TENANT_BASE_DOMAIN` | empty | Base domain for subdomain resolution. Empty disables the middleware. |
| `TENANT_CUSTOM_DOMAIN_LOOKUP` | `true` | Resolve tenants from custom domains. |

## Tests

pytest:

- `unit/test_middleware.py`: the tenant context helpers, path, subdomain and
  custom domain resolution, the redirect for unknown subdomains and error
  handling (together with the API tracking tests).
- `unit/test_tenant_service.py`: creation, lookups, listing, plan updates and
  deactivation.

behave (`features/multi_tenancy.feature`), with the database lookups answered
from an in-memory directory:

- Resolve a tenant from a path prefix
- Resolve a tenant from a subdomain
- Resolve a tenant from a custom domain
- The main domain has no tenant
- An unknown subdomain is redirected to the main domain
- An invalid subdomain is ignored
- An unknown host resolves to no tenant
- A new tenant starts on the free plan
- A tenant slug must be subdomain safe
