# auth

Centralized OIDC/OAuth2 authentication service.

## Features

- Application foundation: Package, settings, logging, health check and Swagger UI.
- Data model and migrations: SQLAlchemy models and the Alembic migration chain.
- Signing keys: Encrypted RSA signing keys and the public JWKS endpoint.
- Multi-tenancy and OIDC discovery: Tenant resolution, issuer, branding, trust policies, outbound webhooks and discovery.
- Outbound webhooks and Celery: Signed webhook deliveries to tenant endpoints through a Celery worker.
- Registration and email verification: User accounts, password hashing, email delivery and verification.
- Sessions and logout: Cookie sessions, sliding expiry middleware and logout.
- Multi-factor authentication: TOTP, email codes and backup codes.
- Login and password reset: Login form and API, password recovery.
- OAuth2 and OIDC authorization server: Clients, authorization code with PKCE, token grants, revocation, introspection and userinfo.
- Device authorization and pushed authorization requests: RFC 8628 device flow and RFC 9126 pushed authorization requests.
- Identity provider federation: Login through external OIDC identity providers.
- REST API v1: Bearer-token JSON API for users, clients, roles, scopes, sessions, keys, tokens and the current user.

## Routes and scopes

HTTP routes served by the application and what each one requires. `public` routes need no credentials. `session` routes need the session cookie of a signed-in user. `PAT` is a personal access token and `bearer token` an OAuth2 access token, both sent in the `Authorization: Bearer` header; the scopes of the token are checked against the scope named in the table (a wildcard scope also matches).

### Service and OpenID Connect endpoints

| Method | Path | Required scope / role / auth | Description |
| --- | --- | --- | --- |
| GET | `/docs` | public | Serve Swagger UI with local static assets (no external CDN dependency) |
| GET | `/docs/oauth2-redirect` | public | OAuth2 redirect page for Swagger UI |
| GET | `/health` | public | Return a liveness signal for load balancers and container probes |
| GET | `/.well-known/openid-configuration` | public | Return the OpenID Connect Discovery metadata document |
| GET | `/.well-known/jwks.json` | public | Return the authorization server's public JSON Web Key Set |
| GET | `/userinfo` | bearer token issued with the `openid` scope | Return OIDC claims for the authenticated end-user (GET) |
| POST | `/userinfo` | bearer token issued with the `openid` scope | Return OIDC claims for the authenticated end-user (POST) |

### OAuth2 and federation

| Method | Path | Required scope / role / auth | Description |
| --- | --- | --- | --- |
| GET | `/oauth2/authorize` | session (redirects to the login page otherwise) | Initiate the OAuth2 authorization code flow |
| POST | `/oauth2/authorize` | session (401 otherwise) | Submit the OAuth2 consent decision and obtain an authorization code |
| POST | `/oauth2/token` | client credentials (HTTP Basic or form); public clients use PKCE with `client_id` only | Issue OAuth2 access tokens for all supported grant types |
| POST | `/oauth2/device` | client authentication (public clients send `client_id` only) | Issue a device code and user code to begin the Device Authorization Grant |
| GET | `/oauth2/device/verify` | session (redirects to the login page otherwise) | Render the user-facing device verification page (RFC 8628 §3.3) |
| POST | `/oauth2/device/verify` | session (redirects to the login page otherwise) | Validate a submitted user code and present the consent screen |
| POST | `/oauth2/device/complete` | session (redirects to the login page otherwise) | Record the user's consent decision and finalize device authorization |
| POST | `/oauth2/par` | client credentials (HTTP Basic or form) | Push an authorization request to the server and receive a request_uri |
| POST | `/oauth2/revoke` | client credentials (HTTP Basic or form) | Revoke an OAuth2 access token or refresh token (RFC 7009) |
| POST | `/oauth2/introspect` | client credentials (HTTP Basic or form), confidential client allowed the `introspect` scope | Validate a token and return its active state and metadata |
| GET | `/federation/providers` | public | List available identity providers for a tenant |
| GET | `/federation/{idp_id}/authorize` | public | Initiate federation flow with an external identity provider |
| GET | `/federation/callback` | public (needs the `code` and `state` returned by the identity provider) | Handle callback from external identity provider |

### Account pages and API

| Method | Path | Required scope / role / auth | Description |
| --- | --- | --- | --- |
| GET | `/auth/register` | public | Render the self-registration HTML form |
| POST | `/auth/register` | public | Process the self-registration form and create a new user account |
| POST | `/auth/register/api` | public | Register a new user account via the JSON API |
| GET | `/auth/verify-email` | public | Render the email verification code entry page |
| POST | `/auth/verify-email` | public | Submit the email verification code via the HTML form |
| POST | `/auth/verify-email/api` | public | Verify an email address using a one-time code (JSON API) |
| POST | `/auth/resend-verification` | public | Re-send the email verification code via the HTML form |
| POST | `/auth/resend-verification/api` | public | Re-send the email verification code (JSON API) |
| GET | `/auth/forgot-password` | public | Render the forgot-password HTML form |
| POST | `/auth/forgot-password` | public | Submit the forgot-password form and dispatch a reset email |
| POST | `/auth/forgot-password/api` | public | Request a password reset link via JSON API |
| GET | `/auth/reset-password` | public | Render the reset-password HTML form authenticated by a URL token |
| POST | `/auth/reset-password` | public | Submit the reset-password form and update the user credential |
| POST | `/auth/reset-password/api` | public | Reset a user password via JSON API using a single-use token |
| GET | `/auth/login` | public | Render the HTML login form for password-based authentication |
| POST | `/auth/login` | public | Process the HTML login form submission and establish a session cookie |
| POST | `/auth/login/api` | public | Authenticate via JSON and establish a session cookie (API variant) |
| POST | `/auth/logout` | public (clears the session cookie) | Terminate the current session and redirect to the login page |
| POST | `/auth/logout/api` | session | Terminate the current session and return a JSON confirmation |
| POST | `/auth/logout/all` | public (clears the session cookie) | Revoke every active session for the user and redirect to the login page |
| POST | `/auth/logout/all/api` | session | Revoke every active session for the user and return a JSON confirmation |
| GET | `/auth/mfa/status` | session | Return TOTP enablement state and backup code counts for the current user |
| POST | `/auth/mfa/totp/setup` | session | Initialise TOTP enrolment for the current user |
| POST | `/auth/mfa/totp/verify` | session | Confirm the pending TOTP secret and activate TOTP for the current user |
| POST | `/auth/mfa/totp/disable` | session | Deactivate TOTP for the current user after confirming the current code |
| POST | `/auth/mfa/backup-codes/regenerate` | session | Invalidate existing backup codes and issue a new set |
| POST | `/auth/mfa/verify` | session | Verify a TOTP code or a single-use backup code during an MFA challenge |
| GET | `/auth/mfa/setup` | session | Render the TOTP enrolment page with a QR code for authenticator apps |
| POST | `/auth/mfa/setup/reconfigure` | session | Replace the active TOTP secret with a newly generated one |
| POST | `/auth/mfa/email/send` | session | Generate and email a time-limited OTP to the current user's primary address |
| POST | `/auth/mfa/email/verify` | session | Validate the email OTP submitted by the current user |
| GET | `/auth/mfa/email` | session | Render the email OTP verification page for browser-based MFA flows |

### REST API v1

| Method | Path | Required scope / role / auth | Description |
| --- | --- | --- | --- |
| GET | `/api/v1/me/` | PAT or bearer token (any scope) | Return the profile of the currently authenticated user |
| PUT | `/api/v1/me/` | PAT or bearer token (any scope) | Replace the profile of the currently authenticated user |
| PUT | `/api/v1/me/password` | PAT or bearer token (any scope) | Change the authenticated user's password |
| GET | `/api/v1/me/sessions` | PAT or bearer token (any scope) | List all active sessions for the current user |
| DELETE | `/api/v1/me/sessions/{session_id}` | PAT or bearer token (any scope) | Revoke a specific session by ID |
| GET | `/api/v1/me/mfa/` | PAT or bearer token (any scope) | Return the current MFA status for the authenticated user |
| POST | `/api/v1/me/mfa/totp/setup` | PAT or bearer token (any scope) | Initiate TOTP setup and return a one-time secret and QR code |
| POST | `/api/v1/me/mfa/totp/verify` | PAT or bearer token (any scope) | Verify a TOTP code and permanently enable TOTP-based MFA |
| POST | `/api/v1/me/mfa/totp/disable` | PAT or bearer token (any scope) | Disable TOTP-based MFA after confirming with a valid TOTP code |
| POST | `/api/v1/me/mfa/backup-codes` | PAT or bearer token (any scope) | Regenerate all backup codes, invalidating the previous set |
| GET | `/api/v1/me/pats/` | PAT or bearer token (any scope) | List all active personal access tokens for the authenticated user |
| POST | `/api/v1/me/pats/` | PAT or bearer token (any scope) | Create a new personal access token for the authenticated user |
| GET | `/api/v1/me/pats/{token_id}` | PAT or bearer token (any scope) | Retrieve metadata for a specific personal access token |
| PATCH | `/api/v1/me/pats/{token_id}` | PAT or bearer token (any scope) | Update the scopes assigned to a personal access token |
| DELETE | `/api/v1/me/pats/{token_id}` | PAT or bearer token (any scope) | Revoke a personal access token, permanently invalidating it |
| POST | `/api/v1/me/pats/{token_id}/regenerate` | PAT or bearer token (any scope) | Regenerate a personal access token, rotating its secret value |
| GET | `/api/v1/me/applications/` | PAT or bearer token (any scope) | List OAuth2 applications the current user has authorized |
| DELETE | `/api/v1/me/applications/{client_id}` | PAT or bearer token (any scope) | Revoke all tokens granted to a specific OAuth2 application |
| GET | `/api/v1/users/` | PAT or bearer token; scope `users:read` | List all users with pagination |
| POST | `/api/v1/users/` | PAT or bearer token; scope `users:write` | Create a new user account |
| GET | `/api/v1/users/{user_id}` | PAT or bearer token; scope `users:read` | Get a single user by ID |
| PATCH | `/api/v1/users/{user_id}` | PAT or bearer token; scope `users:write` | Partially update a user account |
| DELETE | `/api/v1/users/{user_id}` | PAT or bearer token; scope `users:delete` | Permanently delete a user account |
| POST | `/api/v1/users/{user_id}/disable` | PAT or bearer token; scope `users:write` | Disable a user account |
| POST | `/api/v1/users/{user_id}/enable` | PAT or bearer token; scope `users:write` | Enable a previously disabled user account |
| DELETE | `/api/v1/users/{user_id}/sessions` | PAT or bearer token; scope `users:write` | Revoke all active sessions for a user |
| GET | `/api/v1/clients/` | PAT or bearer token; scope `clients:read` | List all OAuth2 clients across all tenants |
| POST | `/api/v1/clients/` | PAT or bearer token; scope `clients:write` | Create a new OAuth2 client |
| GET | `/api/v1/clients/{client_id}` | PAT or bearer token; scope `clients:read` | Get a single OAuth2 client by its internal UUID |
| PATCH | `/api/v1/clients/{client_id}` | PAT or bearer token; scope `clients:write` | Partially update an OAuth2 client's configuration |
| DELETE | `/api/v1/clients/{client_id}` | PAT or bearer token; scope `clients:delete` | Permanently delete an OAuth2 client |
| POST | `/api/v1/clients/{client_id}/rotate-secret` | PAT or bearer token; scope `clients:rotate` | Rotate the client secret for a confidential OAuth2 client |
| GET | `/api/v1/roles/` | PAT or bearer token; scope `roles:read` | List all roles with their assigned scopes |
| POST | `/api/v1/roles/` | PAT or bearer token; scope `roles:write` | Create a new custom role and optionally attach scopes |
| POST | `/api/v1/roles/seed` | PAT or bearer token; scope `roles:write` | Seed the default system roles defined in the application codebase |
| GET | `/api/v1/roles/{role_id}` | PAT or bearer token; scope `roles:read` | Get a single role by ID, including all assigned scopes |
| PATCH | `/api/v1/roles/{role_id}` | PAT or bearer token; scope `roles:write` | Update a role's name, description, or assigned scopes |
| DELETE | `/api/v1/roles/{role_id}` | PAT or bearer token; scope `roles:delete` | Delete a custom role by ID |
| POST | `/api/v1/roles/{role_id}/users` | PAT or bearer token; scope `roles:assign` | Assign a role to a user by user ID |
| DELETE | `/api/v1/roles/{role_id}/users/{target_user_id}` | PAT or bearer token; scope `roles:assign` | Remove a role assignment from a user |
| POST | `/api/v1/roles/{role_id}/scopes/{scope_id}` | PAT or bearer token; scope `roles:write` | Assign a scope to a role by scope ID |
| DELETE | `/api/v1/roles/{role_id}/scopes/{scope_id}` | PAT or bearer token; scope `roles:write` | Remove a scope assignment from a role |
| GET | `/api/v1/scopes/` | PAT or bearer token; scope `scopes:read` | List all scopes with pagination |
| POST | `/api/v1/scopes/` | PAT or bearer token; scope `scopes:write` | Create a new custom scope |
| GET | `/api/v1/scopes/{scope_id}` | PAT or bearer token; scope `scopes:read` | Get a single scope by its UUID |
| PATCH | `/api/v1/scopes/{scope_id}` | PAT or bearer token; scope `scopes:write` | Partially update a scope |
| DELETE | `/api/v1/scopes/{scope_id}` | PAT or bearer token; scope `scopes:delete` | Delete a scope by its UUID |
| GET | `/api/v1/sessions/` | PAT or bearer token; scope `sessions:read` | List all active and revoked sessions across all users |
| GET | `/api/v1/sessions/{session_id}` | PAT or bearer token; scope `sessions:read` | Get a single session by ID |
| DELETE | `/api/v1/sessions/{session_id}` | PAT or bearer token; scope `sessions:revoke` | Revoke a specific session by its ID |
| DELETE | `/api/v1/sessions/` | PAT or bearer token; scope `sessions:revoke` | Revoke all currently active sessions across all users |
| GET | `/api/v1/jwks/` | PAT or bearer token; scope `jwks:read` | List all active JWK keys |
| POST | `/api/v1/jwks/` | PAT or bearer token; scope `jwks:write` | Generate a new JWK key pair |
| POST | `/api/v1/jwks/rotate` | PAT or bearer token; scope `jwks:rotate` | Rotate the active signing key |
| GET | `/api/v1/jwks/{kid}` | PAT or bearer token; scope `jwks:read` | Retrieve a single JWK key by key ID |
| POST | `/api/v1/jwks/{kid}/activate` | PAT or bearer token; scope `jwks:write` | Activate a specific JWK key for token signing |
| POST | `/api/v1/jwks/{kid}/revoke` | PAT or bearer token; scope `jwks:revoke` | Revoke a JWK key |
| DELETE | `/api/v1/jwks/{kid}` | PAT or bearer token; scope `jwks:delete` | Permanently delete a revoked JWK key |
| GET | `/api/v1/pats/` | PAT or bearer token; scope `pats:read` | List all personal access tokens across all users |
| GET | `/api/v1/pats/{pat_id}` | PAT or bearer token; scope `pats:read` | Get a single personal access token by ID (admin view) |
| DELETE | `/api/v1/pats/{pat_id}` | PAT or bearer token; scope `pats:revoke` | Revoke a single personal access token by ID |
| DELETE | `/api/v1/pats/` | PAT or bearer token; scope `pats:revoke` | Revoke active personal access tokens, optionally filtered by user |

### Legacy profile API

| Method | Path | Required scope / role / auth | Description |
| --- | --- | --- | --- |
| GET | `/api/me/profile` | bearer token (any scope) | Get current user's profile |
| PUT | `/api/me/profile` | bearer token (any scope) | Update current user's profile |
| PUT | `/api/me/password` | bearer token (any scope) | Change current user's password |
| GET | `/api/me/mfa/status` | bearer token (any scope) | Get MFA status for current user |
| POST | `/api/me/mfa/totp/setup` | bearer token (any scope) | Start TOTP setup |
| POST | `/api/me/mfa/totp/verify` | bearer token (any scope) | Verify TOTP code and enable MFA |
| POST | `/api/me/mfa/totp/disable` | bearer token (any scope) | Disable TOTP |
| POST | `/api/me/mfa/backup-codes/regenerate` | bearer token (any scope) | Regenerate backup codes |

Static files are served publicly under `/static` (favicon and Swagger UI assets) and `/uploads` (uploaded files).

### Scopes and roles

The scopes and roles of auth itself are defined in the code. The wildcard `*` matches every scope and `<resource>:*` every action on the resource.

Platform scopes (`ADMIN_SCOPES` in `apps/auth/src/auth/db/models/rbac.py`) are the scopes of the authorization of auth itself. They are carried by platform roles assigned to users. The last column counts the routes above that name the scope.

| Scope | Description | Routes |
| --- | --- | --- |
| `*` | Full access to all operations (super admin) | 0 |
| `users:*` | All user operations | 0 |
| `users:read` | View user information (list, details) | 2 |
| `users:write` | Create and update users | 5 |
| `users:delete` | Delete users permanently | 1 |
| `users:disable` | Enable/disable user accounts | 0 |
| `clients:*` | All OAuth2 client operations | 0 |
| `clients:read` | View OAuth2 client information | 2 |
| `clients:write` | Create and update OAuth2 clients | 2 |
| `clients:delete` | Delete OAuth2 clients | 1 |
| `clients:rotate` | Rotate OAuth2 client secrets | 1 |
| `sessions:*` | All session operations | 0 |
| `sessions:read` | View active sessions | 2 |
| `sessions:revoke` | Revoke user sessions | 2 |
| `jwks:*` | All JWKS key operations | 0 |
| `jwks:read` | View JWKS keys (public key info) | 2 |
| `jwks:write` | Create and activate JWKS keys | 2 |
| `jwks:revoke` | Revoke JWKS keys | 1 |
| `jwks:delete` | Delete JWKS keys permanently | 1 |
| `jwks:rotate` | Rotate JWKS keys automatically | 1 |
| `roles:*` | All role operations | 0 |
| `roles:read` | View roles and available scopes | 2 |
| `roles:write` | Create and update custom roles | 5 |
| `roles:delete` | Delete custom roles | 1 |
| `roles:assign` | Assign/remove roles to/from users | 2 |
| `scopes:*` | All scope operations | 0 |
| `scopes:read` | View available scopes | 2 |
| `scopes:write` | Create and update scopes | 2 |
| `scopes:delete` | Delete scopes | 1 |
| `org:*` | All organisation operations | 0 |
| `org:read` | View organisations, their members and identity providers | 0 |
| `org:write` | Create and update organisations, their members and identity providers | 0 |
| `org:delete` | Delete organisations and identity providers | 0 |
| `pats:*` | All PAT management operations (admin) | 0 |
| `pats:read` | View all users' personal access tokens | 2 |
| `pats:revoke` | Revoke any user's personal access tokens | 2 |

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

# Celery worker (outbound webhooks and the other background tasks)
uv run --package auth celery -A auth.celery:celery_app worker -Q auth --loglevel=info

uv run --package auth --group dev pytest apps/auth
uv run --package auth --group dev behave apps/auth/features
```

Settings come from environment variables (a `.env` file is loaded when present). The pytest and behave suites mock the database, Redis and SMTP, so they need no infrastructure.

Documentation: `docs/apps/auth/`.
