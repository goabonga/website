# Data model and migrations

This feature adds the whole persistence layer of the service: the
SQLAlchemy models and the Alembic migration chain that creates the same
schema. The repositories and services that read and write the tables are
introduced one by one by the following features.

## What it does

- Declares 33 tables with SQLAlchemy 2.0 declarative models, grouped in
  `auth.db.models` by domain. Every table carries `created_at` and
  `updated_at` columns (`TimestampMixin`) and the constraint names follow
  the naming convention of `auth.db.base`.
- Provides an Alembic environment (`alembic/env.py`, `alembic.ini`) that
  runs the migrations with the async `asyncpg` engine. `DATABASE_URL`
  overrides the URL of the ini file and `postgresql://` URLs are converted
  to `postgresql+asyncpg://`.
- Ships 33 revisions (`001` to `060`, with gaps) as a single linear chain. The
  migrations only change the schema: no row is inserted, so no deployment
  value (domain, slug, client, scope of another service) is written in a
  migration.
- Provides a `compose.yml` that starts a local PostgreSQL on port 5437 for
  manual runs. The tests do not need it.

## Models

| Module | Tables | Purpose |
| --- | --- | --- |
| `auth.db.models.user` | `users`, `user_emails`, `user_passwords`, `verification_codes`, `password_reset_tokens`, `sessions`, `user_mfas`, `mfa_backup_codes`, `mfa_email_codes`, `user_profiles` | Accounts, credentials, verification and reset codes, sessions, MFA enrolments and profiles |
| `auth.db.models.jwk` | `jwks` | Signing keys |
| `auth.db.models.oauth2` | `oauth2_clients`, `authorization_codes`, `access_tokens`, `refresh_tokens`, `device_codes`, `par_requests` | OAuth2 clients and the tokens and codes they obtain |
| `auth.db.models.rbac` | `scopes`, `roles`, `role_scopes`, `user_roles` | Scopes and global roles |
| `auth.db.models.tenant` | `tenants`, `tenant_members`, `tenant_roles`, `identity_providers`, `federated_identities`, `tenant_branding`, `tenant_templates`, `tenant_trusted_sources`, `tenant_webhooks`, `webhook_deliveries` | Organisations (tenants) and everything they own |
| `auth.db.models.pat` | `personal_access_tokens` | Personal access tokens |
| `auth.db.models.pairwise` | `pairwise_subjects` | Per-tenant pairwise subject identifiers |

`auth.db.models.rbac` also defines `ADMIN_SCOPES` and `DEFAULT_ROLES`, the
built-in scopes and roles of the service itself, which its admin API and
console authorize with. The scopes and roles of the other services of a
deployment are not in the code. The administration of the scopes follows the
`scopes:*` scopes (the `readonly` role holds `scopes:read`, only `super_admin`
can create, change or delete a scope), the one of the roles the `roles:*`
scopes.

`auth.db.models.tenant` defines `TENANT_SCOPES`, the scopes that the roles of
an organisation (`tenant_roles.scopes`) can hold, and `DEFAULT_TENANT_ROLES`,
the three system roles created with every organisation. A role holds a scope
exactly, through the wildcard of its resource (`idp:*`) or through `*`.

| Resource | Scopes |
| --- | --- |
| members | `members:read`, `members:invite`, `members:update`, `members:remove` |
| settings | `settings:read`, `settings:write` (name, e-mail sender, allowed scopes, registration and profile fields) |
| domain | `domain:read`, `domain:write` (the custom domain: set, remove, verify, status) |
| roles | `roles:read`, `roles:write`, `roles:delete` |
| idp | `idp:read`, `idp:write`, `idp:delete` |
| branding | `branding:read`, `branding:write` |
| templates | `templates:read`, `templates:write` |
| clients | `clients:read`, `clients:write`, `clients:delete`, `clients:rotate` |
| trust | `trust:read`, `trust:write` |
| billing | `billing:read`, `billing:write` |
| webhooks | `webhooks:read`, `webhooks:write`, `webhooks:delete` |

Every resource also has its `resource:*` wildcard, and `*` stands for all of
them. The `owner` system role holds `*`; `admin` holds `members:*`,
`settings:read`, `roles:read`, `idp:*`, `branding:*`, `templates:*`,
`clients:read`, `trust:read`, `domain:read` and `webhooks:*`; `member` holds
`members:read`. Only the owner holds `domain:write` by default (the `admin`
role can follow the status of the domain but not change it), and
`settings:*` does not include the `domain` scopes: the custom domain decides
where the sign-in pages of the organisation are served, so changing it is
granted on purpose.
The system roles are created from these constants when an organisation is
created (`create_default_roles`) and are not synchronised afterwards: a scope
added to the constants reaches the owners of existing organisations through
`*`, and appears in the role editor, but is not added to the roles already
stored.

## Tables

| Table | Columns |
| --- | --- |
| `jwks` | `id`, `kid`, `kty`, `alg`, `use`, `private_key_encrypted`, `public_key_pem`, `is_active`, `revoked_at`, `created_at`, `updated_at` |
| `roles` | `id`, `name`, `description`, `is_system`, `created_at`, `updated_at` |
| `scopes` | `id`, `name`, `description`, `resource`, `action`, `category`, `is_system`, `is_active`, `created_at`, `updated_at` |
| `tenants` | `id`, `slug`, `display_name`, `custom_domain`, `custom_domain_status`, `custom_domain_verified_at`, `custom_domain_ssl_at`, `custom_domain_error`, `custom_domain_checked_at`, `is_active`, `is_platform`, `settings`, `trust_mode`, `created_at`, `updated_at` |
| `identity_providers` | `id`, `tenant_id`, `name`, `provider_type`, `discovery_url`, `authorization_endpoint`, `token_endpoint`, `userinfo_endpoint`, `jwks_uri`, `client_id`, `client_secret_encrypted`, `scopes`, `attribute_mapping`, `allowed_domains`, `is_active`, `is_default`, `auto_provision`, `allow_linking`, `icon_url`, `button_text`, `display_order`, `created_at`, `updated_at` |
| `oauth2_clients` | `id`, `client_id`, `client_secret_hash`, `name`, `description`, `homepage_url`, `redirect_uris`, `allowed_scopes`, `allowed_grant_types`, `token_endpoint_auth_method`, `is_confidential`, `is_active`, `require_pkce`, `require_consent`, `jwks_uri`, `request_object_signing_alg`, `allowed_origins`, `access_token_expiry_seconds`, `refresh_token_expiry_seconds`, `tenant_id`, `created_at`, `updated_at` |
| `role_scopes` | `id`, `role_id`, `scope_id`, `created_at`, `updated_at` |
| `tenant_branding` | `id`, `tenant_id`, `logo_url`, `logo_dark_url`, `favicon_url`, `primary_color`, `secondary_color`, `accent_color`, `background_color`, `surface_color`, `text_color`, `text_muted_color`, `error_color`, `success_color`, `border_color`, `warning_color`, `info_color`, `input_background_color`, `input_focus_background_color`, `input_border_color`, `input_focus_border_color`, `input_text_color`, `font_family`, `font_url`, `custom_css`, `custom_js`, `show_powered_by`, `created_at`, `updated_at` |
| `tenant_roles` | `id`, `tenant_id`, `name`, `display_name`, `description`, `scopes`, `is_system`, `is_default`, `display_order`, `created_at`, `updated_at` |
| `tenant_templates` | `id`, `tenant_id`, `template_name`, `content`, `is_active`, `description`, `created_at`, `updated_at` |
| `tenant_trusted_sources` | `id`, `tenant_id`, `trusted_tenant_id`, `description`, `created_at`, `updated_at` |
| `tenant_webhooks` | `id`, `tenant_id`, `name`, `url`, `events`, `secret`, `headers`, `is_active`, `last_triggered_at`, `last_status_code`, `last_error`, `failure_count`, `created_at`, `updated_at` |
| `users` | `id`, `is_active`, `registration_source`, `registration_client_id`, `registration_tenant_id`, `registration_ip`, `registration_user_agent`, `created_at`, `updated_at` |
| `access_tokens` | `id`, `jti`, `client_id`, `user_id`, `scopes`, `expires_at`, `revoked_at`, `created_at`, `updated_at` |
| `authorization_codes` | `id`, `code_hash`, `client_id`, `user_id`, `redirect_uri`, `scopes`, `code_challenge`, `code_challenge_method`, `nonce`, `state`, `expires_at`, `used_at`, `created_at`, `updated_at` |
| `device_codes` | `id`, `device_code_hash`, `user_code`, `client_id`, `user_id`, `scopes`, `status`, `verification_uri`, `interval`, `expires_at`, `last_poll_at`, `created_at`, `updated_at` |
| `federated_identities` | `id`, `user_id`, `identity_provider_id`, `external_subject`, `external_email`, `external_username`, `raw_claims`, `linked_at`, `last_login_at`, `created_at`, `updated_at` |
| `mfa_email_codes` | `id`, `user_id`, `email`, `code_hash`, `expires_at`, `used_at`, `created_at`, `updated_at` |
| `pairwise_subjects` | `id`, `user_id`, `tenant_id`, `sub_value`, `created_at`, `updated_at` |
| `par_requests` | `id`, `request_uri`, `client_id`, `response_type`, `redirect_uri`, `scopes`, `state`, `code_challenge`, `code_challenge_method`, `nonce`, `prompt`, `expires_at`, `used_at`, `created_at`, `updated_at` |
| `password_reset_tokens` | `id`, `user_id`, `email`, `token_hash`, `expires_at`, `used_at`, `created_at`, `updated_at` |
| `personal_access_tokens` | `id`, `user_id`, `name`, `description`, `token_hash`, `token_suffix`, `scopes`, `expires_at`, `tenant_id`, `target_client_id`, `last_used_at`, `last_used_ip`, `use_count`, `revoked_at`, `revoked_by`, `revocation_reason`, `created_at`, `updated_at` |
| `sessions` | `id`, `user_id`, `session_token_hash`, `csrf_token_hash`, `ip_address`, `user_agent`, `expires_at`, `revoked_at`, `tenant_id`, `created_at`, `updated_at` |
| `tenant_members` | `id`, `tenant_id`, `user_id`, `role_id`, `invited_by`, `invited_at`, `joined_at`, `created_at`, `updated_at` |
| `user_emails` | `id`, `user_id`, `email`, `is_verified`, `is_primary`, `verified_at`, `created_at`, `updated_at` |
| `user_mfas` | `id`, `user_id`, `totp_secret_encrypted`, `totp_enabled`, `totp_enabled_at`, `created_at`, `updated_at` |
| `user_passwords` | `id`, `user_id`, `password_hash`, `is_current`, `created_at`, `updated_at` |
| `user_profiles` | `id`, `user_id`, `name`, `given_name`, `family_name`, `middle_name`, `nickname`, `preferred_username`, `profile_url`, `picture_url`, `website`, `gender`, `birthdate`, `zoneinfo`, `locale`, `address_formatted`, `address_street`, `address_locality`, `address_region`, `address_postal_code`, `address_country`, `phone_number`, `phone_number_verified`, `created_at`, `updated_at` |
| `user_roles` | `id`, `user_id`, `role_id`, `assigned_by`, `expires_at`, `created_at`, `updated_at` |
| `verification_codes` | `id`, `user_id`, `email`, `code_hash`, `expires_at`, `used_at`, `created_at`, `updated_at` |
| `webhook_deliveries` | `id`, `webhook_id`, `tenant_id`, `event`, `idempotency_key`, `request_url`, `request_headers`, `request_body`, `status`, `attempt`, `max_attempts`, `next_retry_at`, `response_status`, `response_headers`, `response_body`, `error`, `duration_ms`, `delivered_at`, `created_at`, `updated_at` |
| `mfa_backup_codes` | `id`, `user_mfa_id`, `code_hash`, `used_at`, `created_at`, `updated_at` |
| `refresh_tokens` | `id`, `token_hash`, `access_token_id`, `client_id`, `user_id`, `scopes`, `expires_at`, `revoked_at`, `used_at`, `created_at`, `updated_at` |

## Migrations

The chain starts with `001_create_jwks_table.py` and ends with
`060_add_is_default_to_tenant_roles.py`. Every revision creates or alters
tables and none inserts a row:

- `016_create_scopes_tables` creates the `scopes` and `role_scopes` tables and
  `017_drop_roles_scopes_array` drops the old `roles.scopes` column, so that
  `role_scopes` is the only link between roles and scopes.
- `045_add_platform_tenant` adds the `tenants.is_platform` flag; the platform
  tenant is a row like any other tenant.

The revision ids are those of the original chain (the ids of the revisions that
only inserted rows are simply absent), and the head is `060`.

Apply the migrations from the repository root:

```bash
docker compose -f apps/auth/compose.yml up -d
DATABASE_URL=postgresql://auth:auth@localhost:5437/auth \
  uv run --package auth alembic -c apps/auth/alembic.ini upgrade head
```

## Settings

This feature adds no setting.

`DATABASE_URL` (see the foundation page) is the only setting used by the
migrations.

## Tests

- pytest: 7 new test modules and 1 existing modules extended.
  New modules: `tests/test_alembic_chain.py`, `tests/test_models_jwk.py`, `tests/test_models_oauth2.py`, `tests/test_models_pat.py`, `tests/test_models_rbac.py`, `tests/test_models_tenant.py`, `tests/test_models_user.py`.
  Extended: `tests/test_api_deps.py`.
- behave: `features/data_model.feature` with the scenarios *Every table of the service is declared by the models*, *Relationships between the models resolve*, *The schema can be created from the models*, *The migration history is a single linear chain*, *The migrations create the same tables as the models*, *The migrations only change the schema*.

The behave scenarios build the schema on an in-memory SQLite database. The
support module `features/steps/sqlite_db.py` swaps the PostgreSQL-only
`ARRAY` and `JSONB` column types for `JSON` and the timezone-aware
timestamps for naive UTC ones in the metadata, and wraps a synchronous
session so that the repositories (which `await` an `AsyncSession`) run
unchanged. The following features reuse it to exercise the real repositories,
services and routes end to end.
