# Administration console

A server-rendered administration console under `/admin`, built with Jinja2
templates, for the operators of the platform.

## What it does

### Access

The pages authenticate with the **session cookie** and authorize with the
scopes of the roles of the signed-in user (a role carrying `*` opens
everything). A user without the scope receives `403`, rendered as an HTML
page when the client accepts HTML; a disabled account receives
`403 Account is disabled`. The forms redirect back with a `success` or `error`
message in the query string (post/redirect/get) and take no CSRF token: the
session cookie is the only credential of the console.

An anonymous visitor is redirected (`303`) to `/auth/login?next=<page>` and
comes back to the page after signing in.

The pages only offer what the signed-in user can do: a button, a link or a
form that leads to a route is rendered when the roles of the user hold the
scope that route requires, and left out otherwise (the `permissions` of the
page, computed once by `get_user_admin_permissions`). The route stays the
authority and still answers `403`. Where a page and the route behind it use
different scopes the template follows the route: the scopes pages and the
Scopes entry of the sidebar need `scopes:*` (the scopes API uses the same
scopes; the roles pages need `roles:*`), revoking the sessions of a user
needs `users:write`, the dashboard and its quick actions need the read scope
of the section they open, and the registration fields, profile fields and
allowed scopes of an organisation can only be saved with `org:write`.

Known limitation of the code as migrated:

- the scope dependency also accepts a bearer token, but the page handlers
  expect the (user, roles) pair of a session and fail with a server error for
  a token. Use the REST API for token-based automation.

### Editing a role

`/admin/roles/{role_id}/edit` (`roles:write`) edits the description and the
scopes of a **custom** role; its name cannot be changed. The form lists the
built-in scopes, the other active scopes and the scopes the role holds, and the
scopes that are checked (plus the comma-separated ones typed in the last
field) replace the current ones; a scope that is not known to the database is
refused with a message and nothing is saved. The assignments of disabled scopes
are kept, since the form lists active scopes only. A system role is refused: the
page redirects to the role with the message *System roles cannot be modified*,
and the *Edit Role* button of the detail page is only shown to `roles:write`
for a custom role. The REST route `PATCH /api/v1/roles/{id}` has the same
effect for the description and the scopes (by identifier) and does not refuse
system roles.

### Sections

| Section | Scopes | Pages |
| --- | --- | --- |
| Dashboard `/admin/` | `users:read` | counters: users (total, active, new today, this week, this month), active sessions, clients, roles |
| Users | `users:read/write/delete/disable` | list with search and pagination, detail, create, edit, avatar upload, disable and enable, revoke sessions, delete, bulk delete |
| Clients | `clients:*` | list, detail, create (the secret is shown once), edit, disable and enable, rotate secret, delete, list and revoke the issued tokens |
| Roles | `roles:*` | list, detail, create, edit (description and scopes of a custom role), assign to users, remove from a user, delete, seed the default roles |
| Scopes | `scopes:*` | list, detail, create, activate or deactivate, delete, seed the system scopes |
| Sessions | `sessions:read/revoke` | list, detail, revoke one or all |
| Signing keys | `jwks:*` | list, detail, generate, rotate, activate, revoke, delete |
| Personal access tokens | `pats:read/revoke` | list, detail, revoke one or all |
| Organisations | `org:read/write/delete` | list, create (with the default roles, so that members can be added), edit, disable, enable, delete; members and their roles; identity providers; registration and profile fields; e-mail sender; allowed scopes; branding; e-mail templates; trust policy; custom roles |

The user detail and signing key pages need `JWKS_ENCRYPTION_KEY`, because they
use the MFA and key services.

`services/token_admin.py` backs the client token pages: it lists and revokes
the access and refresh tokens of a client.

## Endpoints

### `admin.dashboard`

| Method | Path | Handler | Summary |
| --- | --- | --- | --- |
| GET | `/admin/` | `admin_dashboard` | Admin dashboard with system statistics. |

### `admin.jwks_pages`

| Method | Path | Handler | Summary |
| --- | --- | --- | --- |
| GET | `/admin/jwks` | `jwks_list_page` | JWKS keys list page. |
| GET | `/admin/jwks/generate` | `jwks_generate_page` | JWKS key generation form page. |
| POST | `/admin/jwks/generate` | `jwks_generate_submit` | Handle JWKS key generation form submission. |
| GET | `/admin/jwks/{kid}` | `jwks_detail_page` | JWKS key detail page. |
| POST | `/admin/jwks/{kid}/activate` | `jwks_activate_submit` | Handle JWKS key activation. |
| POST | `/admin/jwks/{kid}/revoke` | `jwks_revoke_submit` | Handle JWKS key revocation. |
| POST | `/admin/jwks/{kid}/delete` | `jwks_delete_submit` | Handle JWKS key deletion. |
| POST | `/admin/jwks/rotate` | `jwks_rotate_submit` | Handle JWKS key rotation. |

### `admin.sessions_pages`

| Method | Path | Handler | Summary |
| --- | --- | --- | --- |
| GET | `/admin/sessions` | `sessions_list_page` | Sessions list page. |
| GET | `/admin/sessions/{session_id}` | `session_detail_page` | Session detail page. |
| POST | `/admin/sessions/{session_id}/revoke` | `session_revoke_submit` | Handle session revocation. |
| POST | `/admin/sessions/revoke-all` | `sessions_revoke_all_submit` | Handle bulk session revocation. |

### `admin.users_pages`

| Method | Path | Handler | Summary |
| --- | --- | --- | --- |
| GET | `/admin/users` | `users_list_page` | Users list page. |
| GET | `/admin/users/create` | `user_create_page` | User creation form page. |
| POST | `/admin/users/create` | `user_create_submit` | Handle user creation form submission. |
| GET | `/admin/users/{user_id}/edit` | `user_edit_page` | User edit form page. |
| POST | `/admin/users/{user_id}/edit` | `user_edit_submit` | Handle user edit form submission. |
| POST | `/admin/users/{user_id}/avatar` | `user_avatar_upload` | Handle user avatar upload from admin panel. |
| GET | `/admin/users/{user_id}` | `user_detail_page` | User detail page. |
| POST | `/admin/users/{user_id}/disable` | `user_disable_submit` | Handle user disable. |
| POST | `/admin/users/{user_id}/enable` | `user_enable_submit` | Handle user enable. |
| POST | `/admin/users/{user_id}/revoke-sessions` | `user_revoke_sessions_submit` | Handle user sessions revocation. |
| POST | `/admin/users/{user_id}/delete` | `user_delete_submit` | Handle user deletion. |
| POST | `/admin/users/bulk-delete` | `users_bulk_delete` | Handle bulk user deletion. |

### `admin.clients_pages`

| Method | Path | Handler | Summary |
| --- | --- | --- | --- |
| GET | `/admin/clients` | `clients_list_page` | Clients list page. |
| GET | `/admin/clients/create` | `client_create_page` | Client creation form page. |
| POST | `/admin/clients/create` | `client_create_submit` | Handle client creation form submission. |
| GET | `/admin/clients/{client_id}` | `client_detail_page` | Client detail page. |
| GET | `/admin/clients/{client_id}/edit` | `client_edit_page` | Client edit form page. |
| POST | `/admin/clients/{client_id}/edit` | `client_edit_submit` | Handle client edit form submission. |
| POST | `/admin/clients/{client_id}/disable` | `client_disable_submit` | Handle client disable. |
| POST | `/admin/clients/{client_id}/enable` | `client_enable_submit` | Handle client enable. |
| POST | `/admin/clients/{client_id}/rotate-secret` | `client_rotate_secret_submit` | Handle client secret rotation. |
| POST | `/admin/clients/{client_id}/delete` | `client_delete_submit` | Handle client deletion. |
| GET | `/admin/clients/{client_id}/tokens` | `client_tokens_page` | Client tokens list page with advanced filters. |
| POST | `/admin/clients/{client_id}/tokens/{token_id}/revoke` | `client_token_revoke_submit` | Handle token revocation. |
| POST | `/admin/clients/{client_id}/tokens/revoke-all` | `client_tokens_revoke_all_submit` | Handle bulk token revocation for a client. |

### `admin.roles_pages`

| Method | Path | Handler | Summary |
| --- | --- | --- | --- |
| GET | `/admin/roles` | `roles_list_page` | Roles list page. |
| GET | `/admin/roles/create` | `role_create_page` | Role creation form page. |
| POST | `/admin/roles/create` | `role_create_submit` | Handle role creation form submission. |
| GET | `/admin/roles/{role_id}` | `role_detail_page` | Role detail page. |
| GET | `/admin/roles/{role_id}/edit` | `role_edit_page` | Role edit form page (description and scopes of a custom role). |
| POST | `/admin/roles/{role_id}/edit` | `role_edit_submit` | Handle the role edit form: replace the description and the scopes of a custom role. |
| GET | `/admin/roles/{role_id}/assign` | `role_assign_page` | Role assignment page. |
| POST | `/admin/roles/{role_id}/assign` | `role_assign_submit` | Handle role assignment form submission. |
| POST | `/admin/roles/{role_id}/users/{user_id}/remove` | `role_remove_user_submit` | Handle removing user from role. |
| POST | `/admin/roles/{role_id}/delete` | `role_delete_submit` | Handle role deletion. |
| POST | `/admin/roles/seed` | `seed_default_roles_submit` | Seed default system roles. |

### `admin.scopes_pages`

| Method | Path | Handler | Summary |
| --- | --- | --- | --- |
| GET | `/admin/scopes` | `scopes_list_page` | Scopes list page. |
| GET | `/admin/scopes/create` | `scope_create_page` | Scope creation form page. |
| POST | `/admin/scopes/create` | `scope_create_submit` | Handle scope creation form submission. |
| GET | `/admin/scopes/{scope_id}` | `scope_detail_page` | Scope detail page. |
| POST | `/admin/scopes/{scope_id}/toggle` | `scope_toggle_submit` | Handle scope enable/disable toggle. |
| POST | `/admin/scopes/{scope_id}/delete` | `scope_delete_submit` | Handle scope deletion. |
| POST | `/admin/scopes/seed` | `seed_default_scopes_submit` | Seed default system scopes. |

### `admin.tenants_pages`

| Method | Path | Handler | Summary |
| --- | --- | --- | --- |
| GET | `/admin/organisations` | `tenants_list_page` | Tenants list page. |
| GET | `/admin/organisations/create` | `tenant_create_page` | Tenant creation form page. |
| POST | `/admin/organisations/create` | `tenant_create_submit` | Handle tenant creation form submission. |
| GET | `/admin/organisations/{tenant_id}` | `tenant_detail_page` | Tenant detail page. |
| GET | `/admin/organisations/{tenant_id}/edit` | `tenant_edit_page` | Tenant edit form page. |
| POST | `/admin/organisations/{tenant_id}/edit` | `tenant_edit_submit` | Handle tenant edit form submission. |
| POST | `/admin/organisations/{tenant_id}/disable` | `tenant_disable_submit` | Handle tenant disable. |
| POST | `/admin/organisations/{tenant_id}/enable` | `tenant_enable_submit` | Handle tenant enable. |
| POST | `/admin/organisations/{tenant_id}/delete` | `tenant_delete_submit` | Handle tenant deletion. |
| POST | `/admin/organisations/{tenant_id}/members/add` | `tenant_add_member_submit` | Add a member to the tenant. |
| POST | `/admin/organisations/{tenant_id}/members/{member_id}/update-role` | `tenant_update_member_role_submit` | Update a member's role. |
| POST | `/admin/organisations/{tenant_id}/members/{member_id}/remove` | `tenant_remove_member_submit` | Remove a member from the tenant. |
| GET | `/admin/organisations/{tenant_id}/idp/create` | `tenant_idp_create_page` | Identity provider creation form page. |
| POST | `/admin/organisations/{tenant_id}/idp/create` | `tenant_idp_create_submit` | Handle IdP creation form submission. |
| GET | `/admin/organisations/{tenant_id}/idp/{idp_id}/edit` | `tenant_idp_edit_page` | Identity provider edit form page. |
| POST | `/admin/organisations/{tenant_id}/idp/{idp_id}/edit` | `tenant_idp_edit_submit` | Handle IdP edit form submission. |
| POST | `/admin/organisations/{tenant_id}/idp/{idp_id}/delete` | `tenant_idp_delete_submit` | Handle IdP deletion. |
| POST | `/admin/organisations/{tenant_id}/idp/{idp_id}/toggle` | `tenant_idp_toggle_submit` | Toggle IdP active status. |
| GET | `/admin/organisations/{tenant_id}/registration-fields` | `tenant_registration_fields_page` | Registration fields configuration page. |
| POST | `/admin/organisations/{tenant_id}/registration-fields` | `tenant_registration_fields_submit` | Save registration fields configuration. |
| POST | `/admin/organisations/{tenant_id}/email-sender` | `tenant_email_sender_submit` | Save email sender configuration. |
| GET | `/admin/organisations/{tenant_id}/profile-fields` | `tenant_profile_fields_page` | Profile fields configuration page. |
| POST | `/admin/organisations/{tenant_id}/profile-fields` | `tenant_profile_fields_submit` | Save profile fields configuration. |
| GET | `/admin/organisations/{tenant_id}/allowed-scopes` | `tenant_allowed_scopes_page` | Allowed scopes configuration page. |
| POST | `/admin/organisations/{tenant_id}/allowed-scopes` | `tenant_allowed_scopes_submit` | Save allowed scopes configuration. |
| GET | `/admin/organisations/{tenant_id}/branding` | `tenant_branding_page` | Tenant branding edit page. |
| POST | `/admin/organisations/{tenant_id}/branding` | `tenant_branding_submit` | Handle branding form submission. |
| POST | `/admin/organisations/{tenant_id}/branding/reset` | `tenant_branding_reset` | Reset branding to defaults (delete branding record). |
| GET | `/admin/organisations/{tenant_id}/templates` | `tenant_templates_page` | Tenant templates list page. |
| GET | `/admin/organisations/{tenant_id}/templates/{template_name:path}/edit` | `tenant_template_edit_page` | Template edit page. |
| POST | `/admin/organisations/{tenant_id}/templates/{template_name:path}/edit` | `tenant_template_edit_submit` | Handle template edit form submission. |
| POST | `/admin/organisations/{tenant_id}/templates/{template_name:path}/delete` | `tenant_template_delete` | Delete a custom template (reverts to default). |
| POST | `/admin/organisations/{tenant_id}/templates/{template_name:path}/toggle` | `tenant_template_toggle` | Toggle template active status. |
| POST | `/admin/organisations/{tenant_id}/trust/mode` | `tenant_trust_mode_submit` | Update trust mode for a tenant. |
| POST | `/admin/organisations/{tenant_id}/trust/add-source` | `tenant_trust_add_source` | Add a trusted source tenant. |
| POST | `/admin/organisations/{tenant_id}/trust/remove-source/{source_id}` | `tenant_trust_remove_source` | Remove a trusted source. |
| GET | `/admin/organisations/{tenant_id}/roles/create` | `tenant_role_create_page` | Role creation form page. |
| POST | `/admin/organisations/{tenant_id}/roles/create` | `tenant_role_create_submit` | Create a new role. |
| GET | `/admin/organisations/{tenant_id}/roles/{role_id}/edit` | `tenant_role_edit_page` | Role edit form page. |
| POST | `/admin/organisations/{tenant_id}/roles/{role_id}/edit` | `tenant_role_edit_submit` | Update a role. |
| POST | `/admin/organisations/{tenant_id}/roles/{role_id}/delete` | `tenant_role_delete_submit` | Delete a role. |

### `admin.pats_pages`

| Method | Path | Handler | Summary |
| --- | --- | --- | --- |
| GET | `/admin/pats` | `pats_list_page` | PATs list page. |
| GET | `/admin/pats/{token_id}` | `pat_detail_page` | PAT detail page. |
| POST | `/admin/pats/{token_id}/revoke` | `pat_revoke_submit` | Handle PAT revocation. |
| POST | `/admin/pats/revoke-all` | `pats_revoke_all_submit` | Handle bulk PAT revocation for a user. |

## Settings

This feature adds no setting.

## Data model

No new table.

## Tests

- pytest: 8 new test modules.
  New modules: `tests/test_routes_admin_dashboard.py`, `tests/test_routes_admin_pages_clients_tenants.py`, `tests/test_routes_admin_pages_small.py`, `tests/test_routes_admin_pages_tenants_settings.py`, `tests/test_routes_admin_pages_users_roles.py`, `tests/test_token_admin_service.py`, `tests/test_admin_templates_permissions.py` (the controls of the templates against the scope their route requires), `tests/test_routes_admin_role_edit.py` (the role edit page and `RoleService.update_role_by_scope_names`).
- behave: `features/admin_console.feature` with the scenarios *Anonymous visitors are not served*, *A user without an administrator role is refused*, *The dashboard shows aggregate counters*, *The user list and detail pages show accounts*, *An administrator creates a user from the form*, *A password that is too short is refused by the form*, *An administrator disables and enables an account*, *An administrator defines a scope and cannot duplicate it*, *An administrator creates an organisation*, *The signing key pages are reachable*, *A read-only role is not offered the actions it would be refused*, *The role that holds the scope is offered the action*, *The scopes pages follow the scopes scopes, not the roles scopes*, *An administrator edits the description and the scopes of a custom role*, *A system role cannot be edited*, *Editing a role needs the roles:write scope*.

The behave scenarios sign in with a real session cookie and a role holding the
`*` scope, then drive the pages and the forms through the test client: list and
detail pages, user creation and validation, disabling and enabling an account,
scope creation with its duplicate check, organisation creation and the access
rules for anonymous and unprivileged users.

### Browser scenarios

`features/browser/admin_console.feature` is tagged `@browser`: its 20 scenarios drive the
application in Chromium (see [browser tests](../../testing/index.md)).

- Anonymous visitors are sent to the login page and come back after signing in
- A user without an administrator role is refused
- The sidebar opens every section of the console
- A read-only administrator is only offered what the routes allow
- The Scopes entry follows the scopes scopes, not the roles scopes
- An administrator creates a user and finds it in the list
- An administrator disables an account and the user can no longer sign in
- A password that is too short is refused by the form
- An administrator defines a scope and cannot define it twice
- An administrator creates a role and assigns it to a user
- An administrator edits a custom role and cannot edit a system role
- An administrator registers an OAuth2 client and sees its secret once
- An administrator creates a tenant and adds a member from its page
- The customization pages of a tenant open from its page
- An administrator generates a signing key and publishes it
- An administrator revokes a session from the sessions page
- An identity provider created in the console lets members sign in
- An administrator edits the profile of a user
- An administrator rotates the secret of a client
- The access token page explains that there is none yet

The scenarios sign in on the login page and click through the console: the sidebar, the forms, the confirmation dialogs and the redirects. An identity provider created in the console is then used by a visitor to sign in.
