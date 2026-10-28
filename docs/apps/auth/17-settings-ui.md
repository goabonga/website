# Account and organisation settings pages

The self-service area under `/auth/settings` (also reached from `/`, which
redirects there): a signed-in user manages their profile, password, security,
sessions, authorised applications, e-mail addresses, personal access tokens
and organisations, and organisation administrators configure their tenant.

## What it does

### Access

The pages use the session cookie of the tenant. An anonymous visitor is
redirected to `/auth/login` with a `next` parameter; `/auth/settings` itself
always redirects to `/auth/settings/profile`. The JSON variants (suffix `/api`)
answer `401` without a session.

### Account pages

- **Profile**: the OIDC profile fields allowed by the `profile_fields`
  configuration of the tenant, avatar upload (form and JSON), and
  `GET`/`PUT /auth/settings/profile/api`.
- **Password**: the form and `PUT /auth/settings/password/api` with
  `current_password` and `new_password`; a wrong current password or a new
  password shorter than 8 characters answers `400` with an `error`.
- **Security**: MFA status, the link to the enrolment page, and two forms that
  confirm a code from the authenticator app to regenerate the backup codes
  (the new codes are listed in place) or to disable two-factor authentication.
- **Sessions**: list of the active sessions, revocation of one session or all
  the others, and the JSON equivalents.
- **Applications**: the OAuth2 clients the user authorised, with revocation.
- **E-mail addresses**: add an address (a verification code is e-mailed),
  verify it, resend the code, make it primary, remove it.
- **Personal access tokens** (`/auth/settings/tokens`): the page and the JSON
  API to list, create (`201`; the token is shown once), read, change the
  scopes, regenerate and revoke tokens, or revoke them all. A token can only
  request scopes the user holds (`400` otherwise) and needs at least one.
- **Organisations**: the memberships of the user, leaving an organisation,
  unlinking a federated identity, linking another provider of the organisation
  (the button starts the federation flow of that provider under
  `/t/{slug}/federation/{idp_id}/authorize`), and creating an organisation (needs the
  `org:write` scope; the creator becomes owner and the slug is derived from the
  name, with a random suffix when taken).

### Organisation administration (`/auth/settings/org/{tenant_id}`)

For the members whose role grants the matching organisation scope:

- the overview and the edit form, e-mail sender, allowed scopes;
- the custom domain: set or remove it (`domain`), verify it (`verify-domain`)
  and follow its status (`domain-status`);
- members: add, change role, remove;
- roles: list, create, edit, delete;
- identity providers: create, edit, enable or disable, delete;
- branding (with reset), registration fields, profile fields, e-mail
  templates, trust mode and trusted sources;
- OAuth2 clients: list, create, detail, edit, enable or disable, rotate the
  secret, delete;
- webhooks: create, update, toggle, rotate the secret, send a test event,
  replay a delivery.

The pages reuse the services of the REST API and organisation API features, so
the rules (scopes, SSRF check, secret handling) are the same.

#### Scope required by each operation

Every organisation route names the organisation scope it requires, the same
one as the matching route of the organisation REST API. A member holds a scope
when the role lists it, the wildcard of its resource (`idp:*`) or `*`; the
guard (`require_tenant_manager`) has no default scope, so a route that forgot
to name one could not be written. A read scope never lets a member change
anything: `settings:read` only opens the pages that display settings.

| Operation | Scope |
| --- | --- |
| Overview, edit form, registration fields and profile fields pages | `settings:read` |
| Save the name, e-mail sender, allowed scopes, registration fields and profile fields | `settings:write` |
| Follow the verification status of the custom domain (`domain-status`) | `domain:read` |
| Set, change or remove the custom domain, start the DNS verification | `domain:write` |
| Add a member | `members:invite` |
| Change the role of a member | `members:update` |
| Remove a member | `members:remove` |
| List the roles | `roles:read` |
| Create or edit a role (forms and submission) | `roles:write` |
| Delete a role | `roles:delete` |
| Create or edit an identity provider (forms and submission), enable or disable it | `idp:write` |
| Delete an identity provider | `idp:delete` |
| Branding page | `branding:read` |
| Save or reset the branding | `branding:write` |
| List the e-mail templates | `templates:read` |
| Edit, enable or disable, delete a template | `templates:write` |
| Trust policy page | `trust:read` |
| Change the trust mode, add or remove a trusted source | `trust:write` |
| List the OAuth2 clients, show a client | `clients:read` |
| Create, edit, enable or disable a client | `clients:write` |
| Rotate the secret of a client | `clients:rotate` |
| Delete a client | `clients:delete` |
| Create, update, enable or disable a webhook, rotate its secret, send a test event, replay a delivery | `webhooks:write` |
| Delete a webhook | `webhooks:delete` |

The default roles hold `*` (owner); `members:*`, `settings:read`, `roles:read`,
`idp:*`, `branding:*`, `templates:*`, `clients:read`, `trust:read`,
`domain:read` and `webhooks:*` (admin); `members:read` (member). An admin
therefore manages members, identity providers, branding, e-mail templates and
webhooks, and follows the status of the custom domain, but neither saves the
organisation settings (`settings:write`) nor changes roles, clients or the
custom domain; owners keep the exclusive rights that the role rules give them:
only a holder of `*` can promote a member to owner, change the role of another
owner or remove one, and the last owner can be neither demoted nor removed.

#### The custom domain has its own scopes

The custom domain decides where the sign-in pages of the organisation are
served and what the issuer is, so it is not part of `settings:write`. The edit
form saves the name only (a `custom_domain` field posted to it is ignored),
and a separate form posts to `/auth/settings/org/{tenant_id}/domain`, which
requires `domain:write`. A member with `settings:write` but without
`domain:write` can therefore rename the organisation and never touch the
domain, and the edit page does not show the domain to a member holding neither
`domain:read` nor `domain:write`. `settings:*` does not include the `domain`
scopes. Only the owner (`*`) holds `domain:write` by default, and the `admin`
role holds `domain:read` (the status polling): grant `domain:write` to a custom
role when an administrator has to manage the domain. The default roles are
created from the code constants when an organisation is created and are not
synchronised afterwards, so the owners of existing organisations hold the new
scopes through `*` and the role editor lists them, while the admin roles
already stored are unchanged (no `domain:read` for them). The same scopes guard
the REST operations on the custom domain (`.../organisations/{org_id}/domain/`,
see [organisation API](14-organisation-api.md#custom-domain)); the settings
`PATCH` of the REST API only merges the JSON `settings` and never touches the
domain. No role scope deletes an organisation: the deletion
is the platform scope `org:delete` (the admin console and
`DELETE /api/v1/organisations/{org_id}`), and an organisation member can only
leave it.

#### What the pages show

The pages show a control (button, link, form, action column) only to the
members who hold the scope its route requires, and leave it out otherwise; the
route keeps answering `403` on a direct request. The scopes of the signed-in
member are computed once per page: the route builds an `OrgPermissions` from
the membership and hands it to the template as `can`, and the template asks
`can['idp:write']`, with the wildcard rules of the guard. A read-only member
sees the overview, the lists and the forms without their save buttons (the
fields of the branding, registration and profile forms are disabled), the
trust mode as text, and the "Manage" link of the organisations page is shown
to every member who holds `settings:read`, whatever the name of the role.

## Endpoints

### `auth.api.routes`

| Method | Path | Handler | Summary |
| --- | --- | --- | --- |
| GET | `/` | `root_redirect` | Redirect root to user settings page. |

### `auth.settings`

| Method | Path | Handler | Summary |
| --- | --- | --- | --- |
| GET | `/auth/settings` | `settings_index` | Redirect the settings root to the profile page. |
| GET | `/auth/settings/profile` | `settings_profile` | Render the user profile settings page. |
| POST | `/auth/settings/profile` | `settings_profile_update` | Process the profile update form submission. |
| POST | `/auth/settings/profile/avatar` | `settings_upload_avatar` | Process a profile avatar upload via multipart form. |
| POST | `/auth/settings/profile/avatar/api` | `upload_avatar_api` | Upload a profile avatar and return the new URL as JSON. |
| GET | `/auth/settings/profile/api` | `get_profile_api` | Return the current user's profile as a JSON object. |
| PUT | `/auth/settings/profile/api` | `update_profile_api` | Update the current user's profile via JSON body. |
| GET | `/auth/settings/password` | `settings_password` | Render the password change settings page. |
| POST | `/auth/settings/password` | `settings_password_update` | Process the password change form submission. |
| PUT | `/auth/settings/password/api` | `update_password_api` | Change the current user's password via JSON body. |
| GET | `/auth/settings/security` | `settings_security` | Render the security settings page showing MFA status. |
| GET | `/auth/settings/sessions` | `settings_sessions` | Render the active sessions management page. |
| POST | `/auth/settings/sessions/{session_id}/revoke` | `settings_revoke_session` | Revoke a specific session by ID. |
| POST | `/auth/settings/sessions/revoke-all` | `settings_revoke_all_sessions` | Revoke all sessions except the one making this request. |
| GET | `/auth/settings/sessions/api` | `get_sessions_api` | Return all active sessions for the current user as JSON. |
| DELETE | `/auth/settings/sessions/{session_id}/api` | `delete_session_api` | Revoke a specific session via JSON API. |
| GET | `/auth/settings/applications` | `settings_applications` | Render the connected applications (OAuth2 consents) page. |
| POST | `/auth/settings/applications/{client_id}/revoke` | `settings_revoke_application` | Revoke all tokens granted to a specific OAuth2 client. |
| GET | `/auth/settings/applications/api` | `get_applications_api` | Return all OAuth2 applications the current user has authorised as JSON. |
| DELETE | `/auth/settings/applications/{client_id}/api` | `delete_application_api` | Revoke all tokens granted to a specific OAuth2 client via JSON API. |
| GET | `/auth/settings/emails` | `settings_emails` | Render the email addresses management page. |
| GET | `/auth/settings/emails/add` | `settings_add_email_redirect` | Redirect GET requests for the add-email form to the emails page. |
| POST | `/auth/settings/emails/add` | `settings_add_email` | Add a new email address and send a verification email. |
| POST | `/auth/settings/emails/{email_id}/remove` | `settings_remove_email` | Remove a secondary email address from the account. |
| POST | `/auth/settings/emails/{email_id}/set-primary` | `settings_set_primary_email` | Promote a verified email address to be the primary address. |
| GET | `/auth/settings/emails/{email_id}/verify` | `settings_verify_email_redirect` | Redirect GET requests for the verify-email form to the emails page. |
| POST | `/auth/settings/emails/{email_id}/verify` | `settings_verify_email` | Verify an email address using the one-time code sent by email. |
| POST | `/auth/settings/emails/{email_id}/resend-verification` | `settings_resend_email_verification` | Resend the verification email for an unverified address. |
| GET | `/auth/settings/organisations` | `settings_tenants` | Render the organisations (tenant memberships) page. |
| POST | `/auth/settings/organisations/{tenant_id}/leave` | `settings_leave_tenant` | Remove the current user from an organisation. |
| POST | `/auth/settings/organisations/{tenant_id}/unlink-idp/{idp_id}` | `settings_unlink_tenant_idp` | Remove the federated identity link between the user and an org IdP. |
| POST | `/auth/settings/organisations/create` | `settings_create_tenant` | Create a new organisation and grant the creator owner role. |
| GET | `/auth/settings/org/{tenant_id}` | `org_detail_page` | Render the organisation detail dashboard for members with access. |
| GET | `/auth/settings/org/{tenant_id}/edit` | `org_edit_page` | Render the organisation edit form for settings managers. |
| POST | `/auth/settings/org/{tenant_id}/edit` | `org_edit_submit` | Process the organisation edit form submission. |
| POST | `/auth/settings/org/{tenant_id}/email-sender` | `org_email_sender_submit` | Save the outbound email sender address and name for an organisation. |
| POST | `/auth/settings/org/{tenant_id}/allowed-scopes` | `org_allowed_scopes_submit` | Save the list of allowed OAuth2 scopes for an organisation. |
| POST | `/auth/settings/org/{tenant_id}/domain` | `org_domain_submit` | Set, change or remove the custom domain of an organisation. |
| GET | `/auth/settings/org/{tenant_id}/verify-domain` | `org_verify_domain` | Trigger DNS verification for the organisation's custom domain. |
| GET | `/auth/settings/org/{tenant_id}/domain-status` | `org_domain_status` | Return the custom domain verification status for polling. |
| POST | `/auth/settings/org/{tenant_id}/members/add` | `org_add_member_submit` | Add an existing user to the organisation by email address. |
| POST | `/auth/settings/org/{tenant_id}/members/{member_id}/update-role` | `org_update_member_role_submit` | Update an organisation member's assigned role. |
| POST | `/auth/settings/org/{tenant_id}/members/{member_id}/remove` | `org_remove_member_submit` | Remove a member from the organisation. |
| GET | `/auth/settings/org/{tenant_id}/roles` | `org_roles_page` | Render the organisation roles management page. |
| GET | `/auth/settings/org/{tenant_id}/roles/create` | `org_role_create_page` | Render the new-role creation form for the organisation. |
| POST | `/auth/settings/org/{tenant_id}/roles/create` | `org_role_create_submit` | Process the new-role creation form submission. |
| GET | `/auth/settings/org/{tenant_id}/roles/{role_id}/edit` | `org_role_edit_page` | Render the role edit form for an existing custom role. |
| POST | `/auth/settings/org/{tenant_id}/roles/{role_id}/edit` | `org_role_edit_submit` | Process the role edit form submission. |
| POST | `/auth/settings/org/{tenant_id}/roles/{role_id}/delete` | `org_role_delete_submit` | Permanently delete a custom role from the organisation. |
| GET | `/auth/settings/org/{tenant_id}/idp/create` | `org_idp_create_page` | Render the identity provider creation form for org owners. |
| POST | `/auth/settings/org/{tenant_id}/idp/create` | `org_idp_create_submit` | Process the identity provider creation form submission. |
| GET | `/auth/settings/org/{tenant_id}/idp/{idp_id}/edit` | `org_idp_edit_page` | Render the identity provider edit form for org owners. |
| POST | `/auth/settings/org/{tenant_id}/idp/{idp_id}/edit` | `org_idp_edit_submit` | Process the identity provider edit form submission. |
| POST | `/auth/settings/org/{tenant_id}/idp/{idp_id}/toggle` | `org_idp_toggle_submit` | Toggle an identity provider's active status. |
| POST | `/auth/settings/org/{tenant_id}/idp/{idp_id}/delete` | `org_idp_delete_submit` | Permanently delete an identity provider and all its federated identities. |
| GET | `/auth/settings/org/{tenant_id}/branding` | `org_branding_page` | Render the branding customisation page for org owners. |
| POST | `/auth/settings/org/{tenant_id}/branding` | `org_branding_submit` | Process the branding customisation form submission. |
| POST | `/auth/settings/org/{tenant_id}/branding/reset` | `org_branding_reset` | Delete the organisation's custom branding and revert to platform defaults. |
| GET | `/auth/settings/org/{tenant_id}/registration-fields` | `org_registration_fields_page` | Render the registration fields configuration page for org owners. |
| POST | `/auth/settings/org/{tenant_id}/registration-fields` | `org_registration_fields_submit` | Save the registration fields configuration for an organisation. |
| GET | `/auth/settings/org/{tenant_id}/profile-fields` | `org_profile_fields_page` | Render the profile fields visibility configuration page for org owners. |
| POST | `/auth/settings/org/{tenant_id}/profile-fields` | `org_profile_fields_submit` | Save the profile fields visibility configuration for an organisation. |
| GET | `/auth/settings/org/{tenant_id}/clients` | `org_clients_page` | Render the OAuth2 clients list page for the organisation. |
| GET | `/auth/settings/org/{tenant_id}/clients/create` | `org_client_create_page` | Render the OAuth2 client creation form for the organisation. |
| POST | `/auth/settings/org/{tenant_id}/clients/create` | `org_client_create_submit` | Process the OAuth2 client creation form submission. |
| GET | `/auth/settings/org/{tenant_id}/clients/{client_uuid}` | `org_client_detail_page` | Render the OAuth2 client detail page. |
| GET | `/auth/settings/org/{tenant_id}/clients/{client_uuid}/edit` | `org_client_edit_page` | Render the OAuth2 client edit form. |
| POST | `/auth/settings/org/{tenant_id}/clients/{client_uuid}/edit` | `org_client_edit_submit` | Process the OAuth2 client edit form submission. |
| POST | `/auth/settings/org/{tenant_id}/clients/{client_uuid}/disable` | `org_client_disable` | Disable an OAuth2 client, blocking all new token issuance. |
| POST | `/auth/settings/org/{tenant_id}/clients/{client_uuid}/enable` | `org_client_enable` | Re-enable a previously disabled OAuth2 client. |
| POST | `/auth/settings/org/{tenant_id}/clients/{client_uuid}/rotate-secret` | `org_client_rotate_secret` | Rotate the client secret for a confidential OAuth2 client. |
| POST | `/auth/settings/org/{tenant_id}/clients/{client_uuid}/delete` | `org_client_delete` | Permanently delete an OAuth2 client from the organisation. |
| GET | `/auth/settings/org/{tenant_id}/templates` | `org_templates_page` | Render the Jinja2/MJML templates management page for org owners. |
| GET | `/auth/settings/org/{tenant_id}/templates/{template_name:path}/edit` | `org_template_edit_page` | Render the template editor for a specific customisable template. |
| POST | `/auth/settings/org/{tenant_id}/templates/{template_name:path}/edit` | `org_template_edit_submit` | Save a custom template override for the organisation. |
| POST | `/auth/settings/org/{tenant_id}/templates/{template_name:path}/delete` | `org_template_delete` | Delete the tenant's custom template override, reverting to the platform default. |
| POST | `/auth/settings/org/{tenant_id}/templates/{template_name:path}/toggle` | `org_template_toggle` | Toggle a custom template's active status. |
| GET | `/auth/settings/org/{tenant_id}/trust` | `org_trust_page` | Render the trust policy management page for org owners. |
| POST | `/auth/settings/org/{tenant_id}/trust/mode` | `org_trust_mode_submit` | Update the trust mode for the organisation. |
| POST | `/auth/settings/org/{tenant_id}/trust/add-source` | `org_trust_add_source_submit` | Add a trusted source organisation to the allowlist. |
| POST | `/auth/settings/org/{tenant_id}/trust/remove-source/{source_id}` | `org_trust_remove_source_submit` | Remove a trusted source organisation from the allowlist. |
| POST | `/auth/settings/org/{tenant_id}/webhooks/create` | `org_webhook_create_submit` | Create a new outbound webhook subscription for the organisation. |
| POST | `/auth/settings/org/{tenant_id}/webhooks/{webhook_id}/update` | `org_webhook_update_submit` | Update a webhook's name, URL, and subscribed event list. |
| POST | `/auth/settings/org/{tenant_id}/webhooks/{webhook_id}/toggle` | `org_webhook_toggle` | Pause or resume a webhook by toggling its active flag. |
| POST | `/auth/settings/org/{tenant_id}/webhooks/{webhook_id}/rotate-secret` | `org_webhook_rotate_secret` | Rotate the HMAC signing secret for a webhook. |
| POST | `/auth/settings/org/{tenant_id}/webhooks/{webhook_id}/test` | `org_webhook_test` | Send a test ping through the webhook delivery pipeline. |
| POST | `/auth/settings/org/{tenant_id}/webhooks/{webhook_id}/delete` | `org_webhook_delete` | Permanently delete a webhook and cascade-delete all its delivery records. |
| POST | `/auth/settings/org/{tenant_id}/webhooks/{webhook_id}/deliveries/{delivery_id}/replay` | `org_webhook_replay_delivery` | Replay a previous webhook delivery by cloning it into a new delivery row. |

### `auth.tokens`

| Method | Path | Handler | Summary |
| --- | --- | --- | --- |
| GET | `/auth/settings/tokens` | `tokens_page` | Render the Personal Access Token management settings page. |
| GET | `/auth/settings/tokens/api` | `list_tokens` | List all Personal Access Tokens belonging to the current user. |
| POST | `/auth/settings/tokens/api` | `create_token` | Create a new Personal Access Token for the current user. |
| GET | `/auth/settings/tokens/api/{token_id}` | `get_token` | Retrieve metadata for a single Personal Access Token. |
| PATCH | `/auth/settings/tokens/api/{token_id}` | `update_token_scopes` | Update the scope set assigned to an existing Personal Access Token. |
| DELETE | `/auth/settings/tokens/api/{token_id}` | `revoke_token` | Permanently revoke a single Personal Access Token. |
| POST | `/auth/settings/tokens/api/{token_id}/regenerate` | `regenerate_token` | Regenerate a Personal Access Token, preserving its name and scopes. |
| DELETE | `/auth/settings/tokens/api` | `revoke_all_tokens` | Revoke all Personal Access Tokens belonging to the current user. |

## Settings

This feature adds no setting.

## Data model

No new table.

## Tests

- pytest: 8 new test modules and 1 existing modules extended.
  New modules: `tests/test_routes_auth_settings.py`, `tests/test_routes_auth_settings_branches.py`, `tests/test_routes_auth_settings_org_admin.py`, `tests/test_routes_auth_settings_org_core.py`, `tests/test_routes_auth_settings_org_scopes.py`, `tests/test_routes_auth_settings_org_visibility.py`, `tests/test_routes_auth_settings_webhooks.py`, `tests/test_routes_auth_tokens.py`.
  Extended: `tests/test_routes_api_deps_and_admin.py`.
- behave: `features/settings_pages.feature` with the scenarios *The settings root leads to the profile page*, *Anonymous visitors are sent to the login page*, *A signed-in user sees the settings pages*, *The profile is read and updated through the JSON endpoint*, *The password is changed after checking the current one*, *Sessions are listed and revoked*, *A personal access token is created, listed and revoked*, *A token cannot request scopes the user does not hold*, *A user creates an organisation from the settings*, *A secondary e-mail address is added*, *A member holding only settings:read views the organisation but cannot change it*, *A member holding the scope of the operation changes the organisation*, *An organisation admin manages identity providers but not the organisation settings*, *A member is only offered the controls of the scopes they hold*, *A member sees the controls of the scopes of their role and no other*, *The custom domain has its own scope, settings:write does not change it*, *A member holding domain:write sets and removes the custom domain*, *The owner of an organisation sets the custom domain*.

The behave scenarios sign in with a real session cookie, open every account
page, update the profile and the password through the JSON endpoints, list the
sessions, create, list and revoke a personal access token, refuse a token that
asks for scopes the user lacks, and create an organisation and an e-mail
address through the forms. Three scenarios sign in as members of an
organisation whose role holds only some scopes: a member holding only
`settings:read` opens the organisation but gets `403` on the forms that change
it, a member holding `settings:write` saves the organisation, and an admin
opens the identity provider form but cannot save the organisation settings.
The pytest module `test_routes_auth_settings_org_scopes.py` checks the scope of
each of the organisation routes against the table above (`403` without it, the
custom domain routes out of reach of `settings:*`), and
`test_routes_auth_settings_org_visibility.py` renders the real templates for a
member holding the scope of each control (the control is there), for a member
holding every other organisation scope (it is not) and for the owner.

### Browser scenarios

`features/browser/settings_pages.feature` is tagged `@browser`: its 28 scenarios drive the
application in Chromium (see [browser tests](../../testing/index.md)).

- Anonymous visitors are sent to the login page and come back after signing in
- Every page of the settings menu opens
- The profile is updated from the profile page
- A profile picture is uploaded from the profile page
- The password is changed after checking the current one
- A new e-mail address is verified with the code received, then made primary
- An e-mail address that is not primary can be removed after a confirmation
- Two-factor authentication is enabled, its backup codes regenerated and then disabled
- Another session is revoked from the sessions page
- Revoking every other session keeps the current one
- An application that was granted access is listed and can be revoked
- A personal access token is created, used against the API and revoked
- A user allowed to create organizations creates one and becomes its owner
- An owner renames the organization and sets the sender of its e-mails
- A member only sees the controls of the scopes of their role
- A member allowed to rename the organization does not see its custom domain
- A member holding domain:write sets the custom domain and cannot rename the organization
- An owner adds a member, changes the role and removes the member
- An owner defines a custom role with permissions
- The registration fields chosen by an owner change the registration page of the organization
- The colours chosen by an owner brand the login page of the organization
- A member links the identity provider of the organization and can unlink it
- An owner registers an OAuth2 client for the organization and sees its secret once
- An owner subscribes a webhook and sends it a signed test event
- An owner changes the trust policy of the organization
- A member leaves an organization after a confirmation
- The profile fields chosen by an owner change the profile page of the members
- An owner adds an identity provider to the organization and pauses it

The scenarios sign in on the login page and use the settings menu and the forms. The webhook of an organisation is called by the delivery task on a real receiver and its signature is verified; the registration fields, profile fields and colours chosen in the settings are checked on the pages of the organisation, which is reached through the `/t/{slug}` path.
