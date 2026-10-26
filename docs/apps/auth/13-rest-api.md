# REST API v1

A bearer-token JSON API under `/api/v1` to manage the identity resources of
the platform: users, OAuth2 clients, roles, scopes, sessions, signing keys,
personal access tokens, and the account of the caller. It is the canonical
programmatic interface; the administration console and the settings pages of
the later features cover the same ground for browsers.

## What it does

### Authentication and scopes

Every endpoint expects `Authorization: Bearer <token>`. Two kinds of token
are accepted:

- a **personal access token** (PAT), recognised by its `gab_pat_` prefix. It
  carries the scopes chosen when it was created, may expire, and is rejected
  when revoked or when its owner is disabled;
- an **OAuth2 access token** issued by the authorization server. The `jti` is
  looked up in the database, so a revoked or expired token is refused even
  though its signature is valid. The `sub` claim is a pairwise identifier and
  is resolved back to the real user.

The administration endpoints additionally require a scope, checked with
wildcard support (`users:*` grants `users:read`, `*` grants everything). A
missing or invalid token answers `401`, a missing scope `403` with the detail
`Missing required permission: <scope>`. Errors are `{"detail": ...}`
documents. Lists are paginated with `page` (from 1) and `page_size` (20 by
default, 100 at most) and answer `{"items", "total", "page", "page_size"}`.

| Group | Scopes |
| --- | --- |
| `/users` | `users:read`, `users:write`, `users:delete` |
| `/clients` | `clients:read`, `clients:write`, `clients:delete`, `clients:rotate` |
| `/roles` | `roles:read`, `roles:write`, `roles:delete`, `roles:assign` |
| `/scopes` | `scopes:read`, `scopes:write`, `scopes:delete` |
| `/sessions` | `sessions:read`, `sessions:revoke` |
| `/jwks` | `jwks:read`, `jwks:write`, `jwks:rotate`, `jwks:revoke`, `jwks:delete` |
| `/pats` | `pats:read`, `pats:revoke` |
| `/me/...` | any valid token, acting on the token owner |

### Resources

- **Users**: list, create (`201`, `409` for a duplicate address), read,
  partial update (`is_active` and the profile fields), delete, disable,
  enable, and revoke every session of a user.
- **Clients**: CRUD of OAuth2 clients. Creating a confidential client returns
  the `client_secret` once; `rotate-secret` issues a new one. Only the hash is
  stored.
- **Roles and scopes**: CRUD, `POST /roles/seed` to create the default roles,
  assignment of a role to a user (`409` when already assigned) and of scopes to
  a role. Scopes created through the API are never system scopes (`409` for a
  duplicate name).
- **Sessions**: list, read, revoke one or all sessions.
- **Signing keys**: list, generate, rotate, activate, revoke and delete the
  keys managed by the signing keys feature.
- **PATs (administration)**: list, read and revoke the tokens of any user.
- **The caller (`/me`)**: profile (`GET`/`PUT`, with the pairwise `sub`),
  password change, own sessions, MFA (status, TOTP setup/verify/disable, backup
  code regeneration), own PATs (list, create, read, change scopes, revoke,
  regenerate) and the OAuth2 applications the user authorised (list and
  revoke). A new PAT is returned once, in the `token` field.

### Legacy routes

`/api/me/profile`, `/api/me/password` and `/api/me/mfa/...` are older
variants of the same operations, authenticated with an OAuth2 access token.
They are hidden from the OpenAPI document and kept for existing consumers;
new code should use `/api/v1/me`.

## Endpoints

### `me_legacy`

| Method | Path | Handler | Summary |
| --- | --- | --- | --- |
| GET | `/api/me/profile` | `get_profile` | Get current user's profile. |
| PUT | `/api/me/profile` | `update_profile` | Update current user's profile. |
| PUT | `/api/me/password` | `change_password` | Change current user's password. |
| GET | `/api/me/mfa/status` | `get_mfa_status` | Get MFA status for current user. |
| POST | `/api/me/mfa/totp/setup` | `setup_totp` | Start TOTP setup. Returns secret and QR code. |
| POST | `/api/me/mfa/totp/verify` | `verify_and_enable_totp` | Verify TOTP code and enable MFA. Returns backup codes. |
| POST | `/api/me/mfa/totp/disable` | `disable_totp` | Disable TOTP. Requires current TOTP code. |
| POST | `/api/me/mfa/backup-codes/regenerate` | `regenerate_backup_codes` | Regenerate backup codes. Requires current TOTP code. |

### `api.me.profile`

| Method | Path | Handler | Summary |
| --- | --- | --- | --- |
| GET | `/api/v1/me/` | `get_profile` | Return the profile of the currently authenticated user. |
| PUT | `/api/v1/me/` | `update_profile` | Replace the profile of the currently authenticated user. |

### `api.me.password`

| Method | Path | Handler | Summary |
| --- | --- | --- | --- |
| PUT | `/api/v1/me/password` | `change_password` | Change the authenticated user's password. |

### `api.me.sessions`

| Method | Path | Handler | Summary |
| --- | --- | --- | --- |
| GET | `/api/v1/me/sessions` | `list_sessions` | List all active sessions for the current user. |
| DELETE | `/api/v1/me/sessions/{session_id}` | `revoke_session` | Revoke a specific session by ID. |

### `api.me.mfa`

| Method | Path | Handler | Summary |
| --- | --- | --- | --- |
| GET | `/api/v1/me/mfa/` | `get_mfa_status` | Return the current MFA status for the authenticated user. |
| POST | `/api/v1/me/mfa/totp/setup` | `setup_totp` | Initiate TOTP setup and return a one-time secret and QR code. |
| POST | `/api/v1/me/mfa/totp/verify` | `verify_and_enable_totp` | Verify a TOTP code and permanently enable TOTP-based MFA. |
| POST | `/api/v1/me/mfa/totp/disable` | `disable_totp` | Disable TOTP-based MFA after confirming with a valid TOTP code. |
| POST | `/api/v1/me/mfa/backup-codes` | `regenerate_backup_codes` | Regenerate all backup codes, invalidating the previous set. |

### `api.me.pats`

| Method | Path | Handler | Summary |
| --- | --- | --- | --- |
| GET | `/api/v1/me/pats/` | `list_tokens` | List all active personal access tokens for the authenticated user. |
| POST | `/api/v1/me/pats/` | `create_token` | Create a new personal access token for the authenticated user. |
| GET | `/api/v1/me/pats/{token_id}` | `get_token` | Retrieve metadata for a specific personal access token. |
| PATCH | `/api/v1/me/pats/{token_id}` | `update_token_scopes` | Update the scopes assigned to a personal access token. |
| DELETE | `/api/v1/me/pats/{token_id}` | `revoke_token` | Revoke a personal access token, permanently invalidating it. |
| POST | `/api/v1/me/pats/{token_id}/regenerate` | `regenerate_token` | Regenerate a personal access token, rotating its secret value. |

### `api.me.applications`

| Method | Path | Handler | Summary |
| --- | --- | --- | --- |
| GET | `/api/v1/me/applications/` | `list_authorized_applications` | List OAuth2 applications the current user has authorized. |
| DELETE | `/api/v1/me/applications/{client_id}` | `revoke_application_access` | Revoke all tokens granted to a specific OAuth2 application. |

### `api.users`

| Method | Path | Handler | Summary |
| --- | --- | --- | --- |
| GET | `/api/v1/users/` | `list_users` | List all users with pagination. |
| POST | `/api/v1/users/` | `create_user` | Create a new user account. |
| GET | `/api/v1/users/{user_id}` | `get_user` | Get a single user by ID. |
| PATCH | `/api/v1/users/{user_id}` | `update_user` | Partially update a user account. |
| DELETE | `/api/v1/users/{user_id}` | `delete_user` | Permanently delete a user account. |
| POST | `/api/v1/users/{user_id}/disable` | `disable_user` | Disable a user account. |
| POST | `/api/v1/users/{user_id}/enable` | `enable_user` | Enable a previously disabled user account. |
| DELETE | `/api/v1/users/{user_id}/sessions` | `revoke_user_sessions` | Revoke all active sessions for a user. |

### `api.clients`

| Method | Path | Handler | Summary |
| --- | --- | --- | --- |
| GET | `/api/v1/clients/` | `list_clients` | List all OAuth2 clients across all tenants. |
| POST | `/api/v1/clients/` | `create_client` | Create a new OAuth2 client. |
| GET | `/api/v1/clients/{client_id}` | `get_client` | Get a single OAuth2 client by its internal UUID. |
| PATCH | `/api/v1/clients/{client_id}` | `update_client` | Partially update an OAuth2 client's configuration. |
| DELETE | `/api/v1/clients/{client_id}` | `delete_client` | Permanently delete an OAuth2 client. |
| POST | `/api/v1/clients/{client_id}/rotate-secret` | `rotate_client_secret` | Rotate the client secret for a confidential OAuth2 client. |

### `api.roles`

| Method | Path | Handler | Summary |
| --- | --- | --- | --- |
| GET | `/api/v1/roles/` | `list_roles` | List all roles with their assigned scopes. |
| POST | `/api/v1/roles/` | `create_role` | Create a new custom role and optionally attach scopes. |
| POST | `/api/v1/roles/seed` | `seed_default_roles` | Seed the default system roles defined in the application codebase. |
| GET | `/api/v1/roles/{role_id}` | `get_role` | Get a single role by ID, including all assigned scopes. |
| PATCH | `/api/v1/roles/{role_id}` | `update_role` | Update a role's name, description, or assigned scopes. |
| DELETE | `/api/v1/roles/{role_id}` | `delete_role` | Delete a custom role by ID. |
| POST | `/api/v1/roles/{role_id}/users` | `assign_role_to_user` | Assign a role to a user by user ID. |
| DELETE | `/api/v1/roles/{role_id}/users/{target_user_id}` | `remove_role_from_user` | Remove a role assignment from a user. |
| POST | `/api/v1/roles/{role_id}/scopes/{scope_id}` | `assign_scope_to_role` | Assign a scope to a role by scope ID. |
| DELETE | `/api/v1/roles/{role_id}/scopes/{scope_id}` | `remove_scope_from_role` | Remove a scope assignment from a role. |

### `api.scopes`

| Method | Path | Handler | Summary |
| --- | --- | --- | --- |
| GET | `/api/v1/scopes/` | `list_scopes` | List all scopes with pagination. |
| POST | `/api/v1/scopes/` | `create_scope` | Create a new custom scope. |
| GET | `/api/v1/scopes/{scope_id}` | `get_scope` | Get a single scope by its UUID. |
| PATCH | `/api/v1/scopes/{scope_id}` | `update_scope` | Partially update a scope. |
| DELETE | `/api/v1/scopes/{scope_id}` | `delete_scope` | Delete a scope by its UUID. |

### `api.sessions`

| Method | Path | Handler | Summary |
| --- | --- | --- | --- |
| GET | `/api/v1/sessions/` | `list_sessions` | List all active and revoked sessions across all users. |
| GET | `/api/v1/sessions/{session_id}` | `get_session` | Get a single session by ID. |
| DELETE | `/api/v1/sessions/{session_id}` | `revoke_session` | Revoke a specific session by its ID. |
| DELETE | `/api/v1/sessions/` | `revoke_all_sessions` | Revoke all currently active sessions across all users. |

### `api.jwks`

| Method | Path | Handler | Summary |
| --- | --- | --- | --- |
| GET | `/api/v1/jwks/` | `list_keys` | List all active JWK keys. |
| POST | `/api/v1/jwks/` | `generate_key` | Generate a new JWK key pair. |
| POST | `/api/v1/jwks/rotate` | `rotate_keys` | Rotate the active signing key. |
| GET | `/api/v1/jwks/{kid}` | `get_key` | Retrieve a single JWK key by key ID. |
| POST | `/api/v1/jwks/{kid}/activate` | `activate_key` | Activate a specific JWK key for token signing. |
| POST | `/api/v1/jwks/{kid}/revoke` | `revoke_key` | Revoke a JWK key. |
| DELETE | `/api/v1/jwks/{kid}` | `delete_key` | Permanently delete a revoked JWK key. |

### `api.pats`

| Method | Path | Handler | Summary |
| --- | --- | --- | --- |
| GET | `/api/v1/pats/` | `list_pats` | List all personal access tokens across all users. |
| GET | `/api/v1/pats/{pat_id}` | `get_pat` | Get a single personal access token by ID (admin view). |
| DELETE | `/api/v1/pats/{pat_id}` | `revoke_pat` | Revoke a single personal access token by ID. |
| DELETE | `/api/v1/pats/` | `revoke_all_pats` | Revoke active personal access tokens, optionally filtered by user. |

## Settings

This feature adds no setting.

## Data model

No new table: the endpoints work on the users, clients, RBAC, sessions,
signing keys and personal access token tables of the earlier features.

## Tests

- pytest: 24 new test modules and 2 existing modules extended.
  New modules: `tests/api/v1/test_clients.py`, `tests/api/v1/test_jwks.py`, `tests/api/v1/test_me_applications.py`, `tests/api/v1/test_me_mfa.py`, `tests/api/v1/test_me_password.py`, `tests/api/v1/test_me_pats.py`, `tests/api/v1/test_me_profile.py`, `tests/api/v1/test_me_sessions.py`, `tests/api/v1/test_pats.py`, `tests/api/v1/test_roles.py`, `tests/api/v1/test_scopes.py`, `tests/api/v1/test_sessions.py`, `tests/api/v1/test_users.py`, `tests/test_role_service.py`, `tests/test_routes_api_clients.py`, `tests/test_routes_api_deps_and_admin.py`, `tests/test_routes_api_jwks.py`, `tests/test_routes_api_me.py`, `tests/test_routes_api_organisations_branches.py`, `tests/test_routes_api_users.py`, `tests/test_schemas_api_me.py`, `tests/test_schemas_pat.py`, `tests/test_scope_repository.py`, `tests/test_scope_service.py`.
  Extended: `tests/test_api_deps.py`, `tests/test_pairwise_token_integration.py`.
- behave: `features/rest_api.feature` with the scenarios *Requests without a token are refused*, *A token without the required scope is refused*, *An unknown token is refused*, *An administrator manages the lifecycle of a user*, *A duplicate e-mail address is a conflict*, *Custom scopes are created and protected against duplicates*, *A role carries scopes and is assigned to a user*, *An OAuth2 client is created with its secret shown once*, *The current user reads the profile through a token*, *Personal access tokens are listed and revoked by their owner*, *An administrator revokes the sessions of a user*.

The behave scenarios authenticate with real personal access tokens created
through the service and run the repositories against the in-process SQLite
database, so the scope checks, the pagination and the secret handling are
exercised end to end.
