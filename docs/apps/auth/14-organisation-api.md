# Organisation API

JSON endpoints to manage organisations (tenants) and everything that belongs
to one: members, roles, branding, e-mail templates, trust policy, settings,
OAuth2 clients, identity providers, registration and profile fields, e-mail
sender, allowed scopes, custom domain and outbound webhooks.

## What it does

### Two entry points

- `/api/v1/organisations` is the platform view. Listing, creating (`201`,
  `409` for a duplicate slug), reading, updating, deleting, enabling and
  disabling an organisation require the platform scopes `org:read`,
  `org:write` and `org:delete` on the token (read access to one organisation
  is also open to its members).
- `/api/v1/me/organisations` is the self-service view: list the organisations
  the caller belongs to and create a new one. The creator becomes its `owner`
  and the default roles are created with the organisation.

Both prefixes expose the same sub-resources below
`/{org_id}/...`, except the webhooks, which exist under
`/api/v1/organisations/{org_id}/webhooks` only. Authentication is the bearer
token of the REST API feature (personal access token or OAuth2 access token).

### Authorization inside an organisation

Sub-resources check the **membership** of the caller, not the scopes of the
token: the organisation must exist and be active (`404` otherwise), the caller
must be a member (`403 You are not a member of this organisation`) and the
role of the member must grant the scope of the operation (`403 Missing
required permission: <scope>`). The organisation scopes are `members:read`,
`members:invite`, `members:update`, `members:remove`, `settings:read/write`,
`domain:read/write`, `roles:read/write/delete`, `idp:read/write/delete`,
`branding:read/write`, `templates:read/write`,
`clients:read/write/delete/rotate`, `trust:read/write`, `billing:read/write`
and `webhooks:read/write/delete`. The default `owner` role holds all of them.

The `domain` scopes guard the custom domain of the organisation: `domain:read`
for its state, `domain:write` to set, remove and verify it (see
[custom domain](#custom-domain)). `PATCH .../settings/` merges keys into the
JSON `settings` of the organisation and never touches the domain, so
`settings:write` does not give access to it. The default `admin` role holds
`domain:read` only; the `owner` holds all of them through `*`.

### Sub-resources

- **Members**: list, add (a user and optionally a role), change the role,
  remove.
- **Roles**: list, create a custom role from a set of scopes, update (including
  which role is the default for new members), delete.
- **Branding**: read, replace (logo, favicon and the colour palette) and reset.
- **Templates**: list, read, replace, toggle and delete the e-mail templates
  that override the built-in ones.
- **Trust**: read and replace the trust mode, add and remove trusted source
  organisations.
- **Settings, registration fields, profile fields, e-mail sender, allowed
  scopes**: read and patch the tenant configuration that drives the
  registration form, the profile page, the sender of outgoing e-mails and the
  scopes the organisation may grant.
- **Clients**: CRUD of the organisation's OAuth2 clients and secret rotation,
  as for the global API but limited to the tenant.
- **Identity providers**: list, create, update and delete the providers used by
  the federation feature. Client secrets are stored encrypted.
- **Custom domain**: read the state, set, remove and verify the custom domain
  of the organisation.
- **Webhooks**: the catalog of subscribable events (`/webhooks/events`), CRUD
  of the subscriptions (the signing secret is returned once, on creation and on
  `rotate-secret`; the target URL goes through the SSRF check of the webhook
  service), a test delivery, the delivery log and the replay of a delivery.

### Custom domain

The custom domain decides where the sign-in pages of the organisation are
served and what its issuer is. `GET .../domain/` (`domain:read`) returns
`custom_domain`, `status` (`pending`, `dns_verifying`, `dns_verified`,
`ssl_provisioning`, `active` or `failed`, `null` without a domain), `error` and
the `verified_at`, `ssl_at` and `checked_at` dates; poll it after a change.

- `PUT .../domain/` (`domain:write`) with `{"custom_domain": "auth.acme.example"}`
  sets or changes the domain (trimmed and lower-cased). The state becomes
  `pending`, a `tenant.updated` webhook event is dispatched and the DNS
  verification is queued as a Celery task once the change is committed. Setting
  the current domain again changes nothing. `422` for a name that is not a well
  formed host name, `409` when another organisation uses the domain.
- `DELETE .../domain/` (`domain:write`) clears the domain and its state,
  dispatches `tenant.updated` and queues the removal of the configuration of the
  domain (`204`; nothing happens when no domain is set).
- `POST .../domain/verify` (`domain:write`) resets the state to `pending` and
  queues the DNS verification: `202`; `200` with the state when the domain is
  already `active`; `400` without a domain; `409` while a verification or the
  SSL provisioning is running.

The routes and the settings pages call the same service
(`auth.services.custom_domain`), so the state changes, the webhook event and the
tasks are the same whichever entry point is used. The pages do not check the
format of the name that is typed (the DNS verification task does), the API
does.

## Endpoints

### `api.me.organisations`

| Method | Path | Handler | Summary |
| --- | --- | --- | --- |
| GET | `/api/v1/me/organisations/` | `list_my_organisations` | List all organisations the current user belongs to. |
| POST | `/api/v1/me/organisations/` | `create_organisation` | Create a new organisation and assign the current user as owner. |

### `api.me.organisations.members`

| Method | Path | Handler | Summary |
| --- | --- | --- | --- |
| GET | `/api/v1/me/organisations/{org_id}/members/` | `list_members` | List all members of an organisation with pagination. |
| POST | `/api/v1/me/organisations/{org_id}/members/` | `add_member` | Add a user to an organisation as a member. |
| PATCH | `/api/v1/me/organisations/{org_id}/members/{user_id}` | `update_member` | Update the role assigned to an organisation member. |
| DELETE | `/api/v1/me/organisations/{org_id}/members/{user_id}` | `remove_member` | Remove a user from an organisation. |

### `api.me.organisations.roles`

| Method | Path | Handler | Summary |
| --- | --- | --- | --- |
| GET | `/api/v1/me/organisations/{org_id}/roles/` | `list_roles` | List all roles for an organisation. |
| POST | `/api/v1/me/organisations/{org_id}/roles/` | `create_role` | Create a custom role for an organisation. |
| PATCH | `/api/v1/me/organisations/{org_id}/roles/{role_id}` | `update_role` | Update a custom role in an organisation. |
| DELETE | `/api/v1/me/organisations/{org_id}/roles/{role_id}` | `delete_role` | Delete a custom role from an organisation. |

### `api.me.organisations.branding`

| Method | Path | Handler | Summary |
| --- | --- | --- | --- |
| GET | `/api/v1/me/organisations/{org_id}/branding/` | `get_branding` | Retrieve the branding configuration for an organisation. |
| PUT | `/api/v1/me/organisations/{org_id}/branding/` | `update_branding` | Create or replace the branding configuration for an organisation. |
| DELETE | `/api/v1/me/organisations/{org_id}/branding/` | `delete_branding` | Delete the custom branding configuration for an organisation. |

### `api.me.organisations.templates`

| Method | Path | Handler | Summary |
| --- | --- | --- | --- |
| GET | `/api/v1/me/organisations/{org_id}/templates/` | `list_templates` | List all custom templates for an organisation. |
| GET | `/api/v1/me/organisations/{org_id}/templates/{template_name:path}` | `get_template` | Retrieve a single custom template by name for an organisation. |
| PUT | `/api/v1/me/organisations/{org_id}/templates/{template_name:path}` | `update_template` | Create or replace a custom template override for an organisation. |
| POST | `/api/v1/me/organisations/{org_id}/templates/{template_name:path}/toggle` | `toggle_template` | Toggle the active state of a custom template override for an organisation. |
| DELETE | `/api/v1/me/organisations/{org_id}/templates/{template_name:path}` | `delete_template` | Delete a custom template override for an organisation. |

### `api.me.organisations.trust`

| Method | Path | Handler | Summary |
| --- | --- | --- | --- |
| GET | `/api/v1/me/organisations/{org_id}/trust/` | `get_trust_config` | Retrieve the trust configuration for an organisation. |
| PUT | `/api/v1/me/organisations/{org_id}/trust/` | `update_trust_mode` | Update the trust mode for an organisation. |
| POST | `/api/v1/me/organisations/{org_id}/trust/sources` | `add_trusted_source` | Add a trusted source tenant to an organisation. |
| DELETE | `/api/v1/me/organisations/{org_id}/trust/sources/{source_id}` | `remove_trusted_source` | Remove a trusted source tenant from an organisation. |

### `api.me.organisations.settings`

| Method | Path | Handler | Summary |
| --- | --- | --- | --- |
| GET | `/api/v1/me/organisations/{org_id}/settings/` | `get_settings` | Retrieve all settings for an organisation. |
| PATCH | `/api/v1/me/organisations/{org_id}/settings/` | `update_settings` | Partially update settings for an organisation. |

### `api.me.organisations.clients`

| Method | Path | Handler | Summary |
| --- | --- | --- | --- |
| GET | `/api/v1/me/organisations/{org_id}/clients/` | `list_my_org_clients` | List OAuth2 clients belonging to an organisation. |
| POST | `/api/v1/me/organisations/{org_id}/clients/` | `create_my_org_client` | Create a new OAuth2 client for the organisation. |
| GET | `/api/v1/me/organisations/{org_id}/clients/{client_uuid}` | `get_my_org_client` | Get a single OAuth2 client by UUID. |
| PATCH | `/api/v1/me/organisations/{org_id}/clients/{client_uuid}` | `update_my_org_client` | Partially update an OAuth2 client. |
| DELETE | `/api/v1/me/organisations/{org_id}/clients/{client_uuid}` | `delete_my_org_client` | Delete an OAuth2 client. |
| POST | `/api/v1/me/organisations/{org_id}/clients/{client_uuid}/rotate-secret` | `rotate_my_org_client_secret` | Rotate the client secret for a confidential OAuth2 client. |

### `api.me.organisations.idps`

| Method | Path | Handler | Summary |
| --- | --- | --- | --- |
| GET | `/api/v1/me/organisations/{org_id}/idps/` | `list_my_org_idps` | List identity providers configured for an organisation. |
| POST | `/api/v1/me/organisations/{org_id}/idps/` | `create_my_org_idp` | Create a new identity provider for the organisation. |
| PATCH | `/api/v1/me/organisations/{org_id}/idps/{idp_id}` | `update_my_org_idp` | Partially update an identity provider for the organisation. |
| DELETE | `/api/v1/me/organisations/{org_id}/idps/{idp_id}` | `delete_my_org_idp` | Delete an identity provider from the organisation. |

### `api.me.organisations.registration_fields`

| Method | Path | Handler | Summary |
| --- | --- | --- | --- |
| GET | `/api/v1/me/organisations/{org_id}/registration-fields/` | `get_registration_fields` | Return the registration field visibility configuration for an organisation. |
| PATCH | `/api/v1/me/organisations/{org_id}/registration-fields/` | `update_registration_fields` | Update the registration field visibility configuration for an organisation. |

### `api.me.organisations.profile_fields`

| Method | Path | Handler | Summary |
| --- | --- | --- | --- |
| GET | `/api/v1/me/organisations/{org_id}/profile-fields/` | `get_profile_fields` | Return the profile field visibility configuration for the organisation. |
| PATCH | `/api/v1/me/organisations/{org_id}/profile-fields/` | `update_profile_fields` | Update profile field visibility settings for the organisation. |

### `api.me.organisations.email_sender`

| Method | Path | Handler | Summary |
| --- | --- | --- | --- |
| GET | `/api/v1/me/organisations/{org_id}/email-sender/` | `get_email_sender` | Get the email sender configuration for an organisation. |
| PATCH | `/api/v1/me/organisations/{org_id}/email-sender/` | `update_email_sender` | Update the email sender configuration for an organisation. |

### `api.me.organisations.allowed_scopes`

| Method | Path | Handler | Summary |
| --- | --- | --- | --- |
| GET | `/api/v1/me/organisations/{org_id}/allowed-scopes/` | `get_allowed_scopes` | Return the allowed-scopes configuration for an organisation. |
| PATCH | `/api/v1/me/organisations/{org_id}/allowed-scopes/` | `update_allowed_scopes` | Update the allowed-scopes configuration for an organisation. |

### `api.me.organisations.domain`

| Method | Path | Handler | Summary |
| --- | --- | --- | --- |
| GET | `/api/v1/me/organisations/{org_id}/domain/` | `get_custom_domain` | Get the custom domain of an organisation and the state of its verification. |
| PUT | `/api/v1/me/organisations/{org_id}/domain/` | `set_custom_domain` | Set or change the custom domain of an organisation. |
| DELETE | `/api/v1/me/organisations/{org_id}/domain/` | `remove_custom_domain` | Remove the custom domain of an organisation. |
| POST | `/api/v1/me/organisations/{org_id}/domain/verify` | `verify_custom_domain` | Ask for the DNS verification of the custom domain of an organisation. |

### `api.organisations`

| Method | Path | Handler | Summary |
| --- | --- | --- | --- |
| GET | `/api/v1/organisations/` | `list_organisations` | List all organisations with pagination. |
| POST | `/api/v1/organisations/` | `create_organisation` | Create a new organisation. |
| GET | `/api/v1/organisations/{org_id}` | `get_organisation` | Retrieve a single organisation by ID. |
| PATCH | `/api/v1/organisations/{org_id}` | `update_organisation` | Partially update an organisation's attributes. |
| DELETE | `/api/v1/organisations/{org_id}` | `delete_organisation` | Permanently delete an organisation. |
| POST | `/api/v1/organisations/{org_id}/enable` | `enable_organisation` | Enable a previously disabled organisation. |
| POST | `/api/v1/organisations/{org_id}/disable` | `disable_organisation` | Disable an active organisation. |

### `api.organisations.members`

| Method | Path | Handler | Summary |
| --- | --- | --- | --- |
| GET | `/api/v1/organisations/{org_id}/members/` | `list_members` | List all members of an organisation with pagination. |
| POST | `/api/v1/organisations/{org_id}/members/` | `add_member` | Add a user to an organisation. |
| PATCH | `/api/v1/organisations/{org_id}/members/{user_id}` | `update_member` | Update the role assigned to an organisation member. |
| DELETE | `/api/v1/organisations/{org_id}/members/{user_id}` | `remove_member` | Remove a user from an organisation. |

### `api.organisations.roles`

| Method | Path | Handler | Summary |
| --- | --- | --- | --- |
| GET | `/api/v1/organisations/{org_id}/roles/` | `list_roles` | List all roles for an organisation. |
| POST | `/api/v1/organisations/{org_id}/roles/` | `create_role` | Create a custom role for an organisation. |
| PATCH | `/api/v1/organisations/{org_id}/roles/{role_id}` | `update_role` | Update a custom role in an organisation. |
| DELETE | `/api/v1/organisations/{org_id}/roles/{role_id}` | `delete_role` | Delete a custom role from an organisation. |

### `api.organisations.clients`

| Method | Path | Handler | Summary |
| --- | --- | --- | --- |
| GET | `/api/v1/organisations/{org_id}/clients/` | `list_org_clients` | List OAuth2 clients belonging to an organisation. |
| POST | `/api/v1/organisations/{org_id}/clients/` | `create_org_client` | Create a new OAuth2 client for the organisation. |
| GET | `/api/v1/organisations/{org_id}/clients/{client_uuid}` | `get_org_client` | Get a single OAuth2 client by UUID. |
| PATCH | `/api/v1/organisations/{org_id}/clients/{client_uuid}` | `update_org_client` | Partially update an OAuth2 client. |
| DELETE | `/api/v1/organisations/{org_id}/clients/{client_uuid}` | `delete_org_client` | Delete an OAuth2 client. |
| POST | `/api/v1/organisations/{org_id}/clients/{client_uuid}/rotate-secret` | `rotate_org_client_secret` | Rotate the client secret for a confidential OAuth2 client. |

### `api.organisations.idps`

| Method | Path | Handler | Summary |
| --- | --- | --- | --- |
| GET | `/api/v1/organisations/{org_id}/idps/` | `list_org_idps` | List identity providers configured for an organisation. |
| POST | `/api/v1/organisations/{org_id}/idps/` | `create_org_idp` | Create a new identity provider for an organisation. |
| PATCH | `/api/v1/organisations/{org_id}/idps/{idp_id}` | `update_org_idp` | Partially update an identity provider for an organisation. |
| DELETE | `/api/v1/organisations/{org_id}/idps/{idp_id}` | `delete_org_idp` | Delete an identity provider from an organisation. |

### `api.organisations.branding`

| Method | Path | Handler | Summary |
| --- | --- | --- | --- |
| GET | `/api/v1/organisations/{org_id}/branding/` | `get_branding` | Return the branding configuration for an organisation. |
| PUT | `/api/v1/organisations/{org_id}/branding/` | `update_branding` | Create or replace the branding configuration for an organisation. |
| DELETE | `/api/v1/organisations/{org_id}/branding/` | `delete_branding` | Delete the custom branding for an organisation, reverting to defaults. |

### `api.organisations.templates`

| Method | Path | Handler | Summary |
| --- | --- | --- | --- |
| GET | `/api/v1/organisations/{org_id}/templates/` | `list_templates` | List all custom templates for an organisation. |
| GET | `/api/v1/organisations/{org_id}/templates/{template_name:path}` | `get_template` | Get a single custom template for an organisation by name. |
| PUT | `/api/v1/organisations/{org_id}/templates/{template_name:path}` | `update_template` | Create or replace a custom template for an organisation. |
| POST | `/api/v1/organisations/{org_id}/templates/{template_name:path}/toggle` | `toggle_template` | Toggle the active state of a custom template for an organisation. |
| DELETE | `/api/v1/organisations/{org_id}/templates/{template_name:path}` | `delete_template` | Delete a custom template override for an organisation. |

### `api.organisations.trust`

| Method | Path | Handler | Summary |
| --- | --- | --- | --- |
| GET | `/api/v1/organisations/{org_id}/trust/` | `get_trust_config` | Return the trust configuration for an organisation. |
| PUT | `/api/v1/organisations/{org_id}/trust/` | `update_trust_mode` | Set the trust mode for an organisation. |
| POST | `/api/v1/organisations/{org_id}/trust/sources` | `add_trusted_source` | Add a trusted source tenant to an organisation. |
| DELETE | `/api/v1/organisations/{org_id}/trust/sources/{source_id}` | `remove_trusted_source` | Remove a trusted source tenant from an organisation. |

### `api.organisations.settings`

| Method | Path | Handler | Summary |
| --- | --- | --- | --- |
| GET | `/api/v1/organisations/{org_id}/settings/` | `get_settings` | Return all JSONB settings for an organisation. |
| PATCH | `/api/v1/organisations/{org_id}/settings/` | `update_settings` | Partially update JSONB settings for an organisation using shallow merge. |

### `api.organisations.registration_fields`

| Method | Path | Handler | Summary |
| --- | --- | --- | --- |
| GET | `/api/v1/organisations/{org_id}/registration-fields/` | `get_registration_fields` | Get registration field visibility toggles for an organisation. |
| PATCH | `/api/v1/organisations/{org_id}/registration-fields/` | `update_registration_fields` | Update registration field visibility toggles for an organisation. |

### `api.organisations.profile_fields`

| Method | Path | Handler | Summary |
| --- | --- | --- | --- |
| GET | `/api/v1/organisations/{org_id}/profile-fields/` | `get_profile_fields` | Return the profile field visibility toggles for an organisation. |
| PATCH | `/api/v1/organisations/{org_id}/profile-fields/` | `update_profile_fields` | Partially update profile field visibility toggles for an organisation. |

### `api.organisations.email_sender`

| Method | Path | Handler | Summary |
| --- | --- | --- | --- |
| GET | `/api/v1/organisations/{org_id}/email-sender/` | `get_email_sender` | Return the custom email sender configuration for an organisation. |
| PATCH | `/api/v1/organisations/{org_id}/email-sender/` | `update_email_sender` | Update the custom email sender configuration for an organisation. |

### `api.organisations.allowed_scopes`

| Method | Path | Handler | Summary |
| --- | --- | --- | --- |
| GET | `/api/v1/organisations/{org_id}/allowed-scopes/` | `get_allowed_scopes` | Return the allowed-scopes configuration for an organisation. |
| PATCH | `/api/v1/organisations/{org_id}/allowed-scopes/` | `update_allowed_scopes` | Update the allowed-scopes configuration for an organisation. |

### `api.organisations.domain`

| Method | Path | Handler | Summary |
| --- | --- | --- | --- |
| GET | `/api/v1/organisations/{org_id}/domain/` | `get_custom_domain` | Return the custom domain of an organisation and the state of its verification. |
| PUT | `/api/v1/organisations/{org_id}/domain/` | `set_custom_domain` | Set or change the custom domain of an organisation. |
| DELETE | `/api/v1/organisations/{org_id}/domain/` | `remove_custom_domain` | Remove the custom domain of an organisation. |
| POST | `/api/v1/organisations/{org_id}/domain/verify` | `verify_custom_domain` | Ask for the DNS verification of the custom domain of an organisation. |

### `api.organisations.webhooks`

| Method | Path | Handler | Summary |
| --- | --- | --- | --- |
| GET | `/api/v1/organisations/{org_id}/webhooks/events` | `list_org_webhook_events` | List all subscribable webhook event types for an organisation. |
| GET | `/api/v1/organisations/{org_id}/webhooks/` | `list_org_webhooks` | List all webhooks registered for an organisation. |
| POST | `/api/v1/organisations/{org_id}/webhooks/` | `create_org_webhook` | Create a new webhook endpoint for an organisation. |
| GET | `/api/v1/organisations/{org_id}/webhooks/{webhook_id}` | `get_org_webhook` | Retrieve a single webhook by ID. |
| PATCH | `/api/v1/organisations/{org_id}/webhooks/{webhook_id}` | `update_org_webhook` | Partially update a webhook's configuration. |
| DELETE | `/api/v1/organisations/{org_id}/webhooks/{webhook_id}` | `delete_org_webhook` | Permanently delete a webhook and its delivery history. |
| POST | `/api/v1/organisations/{org_id}/webhooks/{webhook_id}/rotate-secret` | `rotate_org_webhook_secret` | Rotate the HMAC-SHA256 signing secret for a webhook. |
| POST | `/api/v1/organisations/{org_id}/webhooks/{webhook_id}/test` | `test_org_webhook` | Send a test delivery to verify a webhook endpoint is reachable. |
| GET | `/api/v1/organisations/{org_id}/webhooks/{webhook_id}/deliveries` | `list_org_webhook_deliveries` | List delivery attempts for a specific webhook. |
| POST | `/api/v1/organisations/{org_id}/webhooks/{webhook_id}/deliveries/{delivery_id}/replay` | `replay_org_webhook_delivery` | Replay a past webhook delivery with a fresh envelope. |

## Settings

This feature adds no setting.

## Data model

No new table; the endpoints use the tenant tables introduced with
multi-tenancy, the webhook tables and the identity provider tables.

## Tests

- pytest: 27 new test modules and 1 existing modules extended.
  New modules: `tests/api/v1/test_me_organisations.py`, `tests/api/v1/test_me_organisations_allowed_scopes.py`, `tests/api/v1/test_me_organisations_branding.py`, `tests/api/v1/test_me_organisations_clients.py`, `tests/api/v1/test_me_organisations_email_sender.py`, `tests/api/v1/test_me_organisations_idps.py`, `tests/api/v1/test_me_organisations_members.py`, `tests/api/v1/test_me_organisations_profile_fields.py`, `tests/api/v1/test_me_organisations_registration_fields.py`, `tests/api/v1/test_me_organisations_roles.py`, `tests/api/v1/test_me_organisations_settings.py`, `tests/api/v1/test_me_organisations_templates.py`, `tests/api/v1/test_me_organisations_trust.py`, `tests/api/v1/test_organisations.py`, `tests/api/v1/test_organisations_allowed_scopes.py`, `tests/api/v1/test_organisations_branding.py`, `tests/api/v1/test_organisations_clients.py`, `tests/api/v1/test_organisations_email_sender.py`, `tests/api/v1/test_organisations_idps.py`, `tests/api/v1/test_organisations_members.py`, `tests/api/v1/test_organisations_profile_fields.py`, `tests/api/v1/test_organisations_registration_fields.py`, `tests/api/v1/test_organisations_roles.py`, `tests/api/v1/test_organisations_settings.py`, `tests/api/v1/test_organisations_templates.py`, `tests/api/v1/test_organisations_trust.py`, `tests/api/v1/test_organisations_webhooks.py`.
  Extended: `tests/test_routes_api_organisations_branches.py`.
- behave: `features/organisation_api.feature` with the scenarios *A platform administrator needs an organisation scope*, *A platform administrator manages an organisation*, *A user creates an organisation and becomes its owner*, *An owner invites and removes a member*, *A member without the permission cannot invite*, *A stranger cannot read an organisation*, *An owner defines a custom role*, *An owner customises the branding*, *An owner registers a webhook*.

- pytest (custom domain): `tests/api/v1/test_organisations_domain.py` runs every operation under both prefixes, with the real membership guard for the scopes, and `tests/test_custom_domain_service.py` covers the service. `tests/test_tenant_service.py` and `tests/test_tenant_repository.py` are extended with the lookup by custom domain.
- behave (custom domain): the scenarios *An owner sets, verifies and removes the custom domain*, *The custom domain is also served under the platform prefix*, *A domain is refused when it is malformed or used by another organisation*, *The admin role follows the custom domain but cannot change it* and *A member without a domain scope sees nothing of the domain*.

The behave scenarios create organisations through both prefixes, check the
membership rules with an owner, a plain member and a stranger, and register a
webhook with the private-network check relaxed so that no DNS lookup is needed.
