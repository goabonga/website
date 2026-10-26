# auth

Centralized OIDC/OAuth2 authentication service.

## Features

- Application foundation: Package, settings, logging, health check and Swagger UI.
- Data model and migrations: SQLAlchemy models and the Alembic migration chain.
- Signing keys: Encrypted RSA signing keys and the public JWKS endpoint.

## Routes and scopes

HTTP routes served by the application and what each one requires. `public` routes need no credentials.

### Service and OpenID Connect endpoints

| Method | Path | Required scope / role / auth | Description |
| --- | --- | --- | --- |
| GET | `/docs` | public | Serve Swagger UI with local static assets (no external CDN dependency) |
| GET | `/docs/oauth2-redirect` | public | OAuth2 redirect page for Swagger UI |
| GET | `/health` | public | Return a liveness signal for load balancers and container probes |
| GET | `/.well-known/jwks.json` | public | Return the authorization server's public JSON Web Key Set |

Static files are served publicly under `/static` (favicon and Swagger UI assets).

### Scopes and roles

The scopes and roles of auth itself are defined in the code. The wildcard `*` matches every scope and `<resource>:*` every action on the resource.

Platform scopes (`ADMIN_SCOPES` in `apps/auth/src/auth/db/models/rbac.py`) are the scopes of the authorization of auth itself. They are carried by platform roles assigned to users.

| Scope | Description |
| --- | --- |
| `*` | Full access to all operations (super admin) |
| `users:*` | All user operations |
| `users:read` | View user information (list, details) |
| `users:write` | Create and update users |
| `users:delete` | Delete users permanently |
| `users:disable` | Enable/disable user accounts |
| `clients:*` | All OAuth2 client operations |
| `clients:read` | View OAuth2 client information |
| `clients:write` | Create and update OAuth2 clients |
| `clients:delete` | Delete OAuth2 clients |
| `clients:rotate` | Rotate OAuth2 client secrets |
| `sessions:*` | All session operations |
| `sessions:read` | View active sessions |
| `sessions:revoke` | Revoke user sessions |
| `jwks:*` | All JWKS key operations |
| `jwks:read` | View JWKS keys (public key info) |
| `jwks:write` | Create and activate JWKS keys |
| `jwks:revoke` | Revoke JWKS keys |
| `jwks:delete` | Delete JWKS keys permanently |
| `jwks:rotate` | Rotate JWKS keys automatically |
| `roles:*` | All role operations |
| `roles:read` | View roles and available scopes |
| `roles:write` | Create and update custom roles |
| `roles:delete` | Delete custom roles |
| `roles:assign` | Assign/remove roles to/from users |
| `scopes:*` | All scope operations |
| `scopes:read` | View available scopes |
| `scopes:write` | Create and update scopes |
| `scopes:delete` | Delete scopes |
| `org:*` | All organisation operations |
| `org:read` | View organisations, their members and identity providers |
| `org:write` | Create and update organisations, their members and identity providers |
| `org:delete` | Delete organisations and identity providers |
| `pats:*` | All PAT management operations (admin) |
| `pats:read` | View all users' personal access tokens |
| `pats:revoke` | Revoke any user's personal access tokens |

Platform roles (`DEFAULT_ROLES`, system roles):

| Role | Description | Scopes |
| --- | --- | --- |
| `super_admin` | Full access to all admin operations | `*` |
| `admin` | Manage users, clients, and sessions | `users:*`, `clients:*`, `sessions:*` |
| `user_manager` | Manage users only | `users:read`, `users:write`, `users:disable`, `sessions:read`, `sessions:revoke` |
| `client_manager` | Manage OAuth2 clients | `clients:*` |
| `jwks_admin` | Manage JWKS keys | `jwks:*` |
| `security_admin` | Security operations (sessions, JWKS) | `sessions:*`, `jwks:*` |
| `readonly` | Read-only access to all resources | `users:read`, `clients:read`, `sessions:read`, `jwks:read`, `roles:read`, `scopes:read` |
| `operator` | Read access + session revocation | `users:read`, `clients:read`, `sessions:read`, `sessions:revoke` |

Organisation scopes (`TENANT_SCOPES` in `apps/auth/src/auth/db/models/tenant.py`) are carried by the role of a member inside an organisation.

| Scope | Description |
| --- | --- |
| `*` | Full access to all tenant operations |
| `members:*` | All member operations |
| `members:read` | View tenant members |
| `members:invite` | Invite new members |
| `members:update` | Update member roles |
| `members:remove` | Remove members from tenant |
| `settings:*` | All settings operations |
| `settings:read` | View tenant settings |
| `settings:write` | Modify tenant settings (name, e-mail sender, allowed scopes, fields) |
| `domain:*` | All custom domain operations |
| `domain:read` | View the custom domain and its verification status |
| `domain:write` | Set, remove and verify the custom domain |
| `roles:*` | All role operations |
| `roles:read` | View tenant roles |
| `roles:write` | Create and modify custom roles |
| `roles:delete` | Delete custom roles |
| `idp:*` | All identity provider operations |
| `idp:read` | View identity provider configurations |
| `idp:write` | Configure identity providers |
| `idp:delete` | Delete identity providers |
| `branding:*` | All branding operations |
| `branding:read` | View branding settings |
| `branding:write` | Modify branding (colors, logos, CSS) |
| `templates:*` | All template operations |
| `templates:read` | View custom templates |
| `templates:write` | Modify custom templates |
| `clients:*` | All OAuth2 client operations |
| `clients:read` | View organization's OAuth2 clients |
| `clients:write` | Create and modify OAuth2 clients |
| `clients:delete` | Delete OAuth2 clients |
| `clients:rotate` | Rotate OAuth2 client secrets |
| `trust:*` | All trust policy operations |
| `trust:read` | View trust policy settings |
| `trust:write` | Modify trust policy |
| `billing:*` | All billing operations |
| `billing:read` | View billing information |
| `billing:write` | Modify billing settings |
| `webhooks:*` | All webhook operations |
| `webhooks:read` | View webhook configurations and deliveries |
| `webhooks:write` | Create and modify webhooks |
| `webhooks:delete` | Delete webhooks |

Default organisation roles (`DEFAULT_TENANT_ROLES`):

| Role | Description | Scopes |
| --- | --- | --- |
| `owner` | Full control over the organization, including managing other owners | `*` |
| `admin` | Can manage members, IdPs, branding, and templates (except owner roles) | `members:*`, `settings:read`, `roles:read`, `idp:*`, `branding:*`, `templates:*`, `clients:read`, `trust:read`, `domain:read`, `webhooks:*` |
| `member` | Basic access to organization resources | `members:read` |

Built-in protocol scopes (`BUILTIN_SCOPES`), always listed next to the stored scopes by the scope selectors: `openid` - OpenID Connect authentication; `profile` - User profile information (name, picture, etc.); `email` - User email address and verification status; `offline_access` - Refresh tokens for offline access; `introspect` - Introspect tokens (RFC 7662).

## Development

From the repository root:

```bash
# Local PostgreSQL (and the other services the features need)
docker compose -f apps/auth/compose.yml up -d

# Apply the database migrations
DATABASE_URL=postgresql://auth:auth@localhost:5437/auth \
  uv run --package auth alembic -c apps/auth/alembic.ini upgrade head

uv sync --package auth
uv run --package auth uvicorn auth.main:app --reload --port 8000

uv run --package auth --group dev pytest apps/auth
uv run --package auth --group dev behave apps/auth/features
```

Settings come from environment variables (a `.env` file is loaded when present). The pytest and behave suites mock the database, Redis and SMTP, so they need no infrastructure.

Documentation: `docs/apps/auth/`.
