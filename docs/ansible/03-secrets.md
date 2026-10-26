# Secrets

Secrets reach the applications in two stages: you keep them in an Ansible
Vault, and the `python_app` role stores them on the host as encrypted systemd
credentials. They never appear in an environment file, in the unit or in the
command line of a process.

## The vault

The example keeps every secret in `inventory/group_vars/all/vault.yml`, with
names that start with `vault_`:

```yaml
vault_auth_jwks_encryption_key: "..."
vault_openai_api_key: "..."
```

```bash
cp inventory/group_vars/all/vault.yml.example inventory/group_vars/all/vault.yml
ansible-vault encrypt inventory/group_vars/all/vault.yml   # then edit with:
ansible-vault edit inventory/group_vars/all/vault.yml
```

`ansible.cfg` points `vault_password_file` to `.vault_pass`. Keep that file out
of version control and out of the encrypted repository; in CI, write it from a
protected secret.

The unencrypted `vault.yml.example` lists every variable of the vault with a
placeholder (`CHANGE_ME`). The variables that are not commented out are the
ones the example inventory needs as it is; the commented ones belong to
applications and roles it does not enable, so uncomment those of what you
enable and leave the others out. [Variables of the vault](#variables-of-the-vault)
says what each one is for.

Variables of the vault are not used directly. They are referenced from
`website_secrets`, in `apps.yml`, so the mapping between a secret and the
application that receives it is visible next to the rest of the configuration.

## What a component receives

`website_secrets` is keyed by application (or component), then by the name the
application reads:

```yaml
website_secrets:
  backend:
    OPENAI_API_KEY: "{{ vault_openai_api_key }}"
    OAUTH2_CLIENT_SECRET: "{{ vault_backend_oauth2_client_secret }}"
  backend_worker:
    OPENAI_API_KEY: "{{ vault_openai_api_key }}"
```

- An **application-level** entry (`backend`) is shared by every component of
  the application that declares the name in `secret_names` or
  `optional_secret_names`. The worker above needs no entry of its own unless it
  uses a different value.
- A **component-level** entry (`backend_worker`) wins over the application one
  and may use any name.
- Each component declares what it needs in the catalog: names in `secret_names`
  must be provided (the run stops otherwise, unless
  `website_secrets_required: false`), names in `optional_secret_names` are
  deployed only when set to a non-empty value.

The catalog lists, for each component, the names the application reads; see
the component table on [Deploying applications](05-deploying-apps.md).

## How they are stored

For each secret the role runs `systemd-creds encrypt` and writes
`/etc/credstore.encrypted/<unit>.<NAME>.cred` (directory mode 0700, owned by
root). The unit loads it with `LoadCredentialEncrypted=NAME:...`, systemd
decrypts it at start into a private, memory-backed directory, and the
application reads it from `$CREDENTIALS_DIRECTORY/NAME`.

- Credentials are bound to the host key (`/var/lib/systemd/credential.secret`
  and the TPM when there is one). A copy of the files is useless on another
  host, and a rebuilt host needs a new run to re-encrypt them.
- The environment file (`/opt/<app>/env/<unit>.env`, mode 0600) holds
  configuration only.
- Tasks that handle secret values run with `no_log`, so they are not printed
  with `-v`.

## Rotation

Change the value in the vault and run the `apps` playbook. The role decrypts
the stored credential, compares it with the new value and only re-encrypts and
restarts the unit when they differ.

## Variables of the vault

Every variable of `vault.yml.example`, with the setting that receives it and
when it is needed. "Required when" is about enabling the application or the
role named: nothing else of the vault is read. Names ending in `_client_id`
are identifiers, not secrets; the example keeps them in the vault with the rest
of the OAuth2 configuration. A client secret or identifier is the one shown by
auth when the client is registered.

| Variable | Used by | Required when | How to generate |
| --- | --- | --- | --- |
| `vault_website_repo_token` | `website_repo_token` (clone of the repository) | Optional: only when the repository is private | Fine-grained token with read access to the repository |
| `vault_frontend_oauth2_client_id` | `website_oauth2_clients.frontend.client_id` | `frontend` is enabled (example inventory) | Client identifier shown by auth when the client is registered |
| `vault_backend_oauth2_client_id` | `website_oauth2_clients.backend.client_id` | `backend` is enabled (example inventory) | Client identifier shown by auth when the client is registered |
| `vault_backend_oauth2_swagger_client_id` | `website_oauth2_clients.backend.swagger_client_id` | `backend` is enabled (example inventory) | Client identifier shown by auth when the client is registered (public client of the Swagger UI) |
| `vault_analytics_oauth2_client_id` | `website_oauth2_clients.analytics.client_id` | `analytics` is enabled (example inventory) | Client identifier shown by auth when the client is registered |
| `vault_analytics_oauth2_swagger_client_id` | `website_oauth2_clients.analytics.swagger_client_id` | `analytics` is enabled (example inventory) | Client identifier shown by auth when the client is registered (public client of the Swagger UI) |
| `vault_apt_server_oauth2_client_id` | `website_oauth2_clients.apt_server.client_id` | `apt_server` is enabled | Client identifier shown by auth when the client is registered |
| `vault_billing_oauth2_client_id` | `website_oauth2_clients.billing.client_id` | `billing` is enabled | Client identifier shown by auth when the client is registered |
| `vault_custom_domain_oauth2_client_id` | `website_oauth2_clients.custom_domain.client_id` | `custom_domain` is enabled | Client identifier shown by auth when the client is registered |
| `vault_internal_oauth2_client_id` | `website_oauth2_clients.internal.client_id` | `internal` is enabled | Client identifier shown by auth when the client is registered |
| `vault_mailler_oauth2_client_id` | `website_oauth2_clients.mailler.client_id` | `mailler` is enabled | Client identifier shown by auth when the client is registered |
| `vault_reachy_mini_api_oauth2_client_id` | `website_oauth2_clients.reachy_mini_api.client_id` | `reachy_mini_api` is enabled | Client identifier shown by auth when the client is registered |
| `vault_team_oauth2_client_id` | `website_oauth2_clients.team.client_id` | `team` is enabled | Client identifier shown by auth when the client is registered |
| `vault_vpn_portal_oauth2_client_id` | `website_oauth2_clients.vpn_portal.client_id` | `vpn_portal` is enabled | Client identifier shown by auth when the client is registered |
| `vault_webhooks_oauth2_client_id` | `website_oauth2_clients.webhooks.client_id` | `webhooks` is enabled and forwards events to mailler | Client identifier shown by auth when the client is registered |
| `vault_vpn_portal_openvpn_oauth2_client_id` | `website_oauth2_clients.vpn_portal.openvpn_client_id` | `vpn_portal_openvpn` (OpenVPN hooks of vpn_portal) is enabled | Client identifier shown by auth when the client is registered |
| `vault_backend_oauth2_client_secret` | `OAUTH2_CLIENT_SECRET` in `website_secrets` of `backend` | `backend` is enabled (example inventory) | Client secret shown by auth when the client is registered |
| `vault_analytics_oauth2_client_secret` | `OAUTH2_CLIENT_SECRET` in `website_secrets` of `analytics` | `analytics` is enabled (example inventory) | Client secret shown by auth when the client is registered |
| `vault_apt_server_oauth2_client_secret` | `OAUTH2_CLIENT_SECRET` in `website_secrets` of `apt_server` | `apt_server` is enabled | Client secret shown by auth when the client is registered |
| `vault_billing_oauth2_client_secret` | `OAUTH2_CLIENT_SECRET` in `website_secrets` of `billing` | `billing` is enabled | Client secret shown by auth when the client is registered |
| `vault_custom_domain_oauth2_client_secret` | `OAUTH2_CLIENT_SECRET` in `website_secrets` of `custom_domain` | `custom_domain` is enabled | Client secret shown by auth when the client is registered |
| `vault_internal_oauth2_client_secret` | `OAUTH2_CLIENT_SECRET` in `website_secrets` of `internal` | `internal` is enabled | Client secret shown by auth when the client is registered |
| `vault_mailler_oauth2_client_secret` | `OAUTH2_CLIENT_SECRET` in `website_secrets` of `mailler` | `mailler` is enabled | Client secret shown by auth when the client is registered |
| `vault_reachy_mini_api_oauth2_client_secret` | `OAUTH2_CLIENT_SECRET` in `website_secrets` of `reachy_mini_api` | `reachy_mini_api` is enabled | Client secret shown by auth when the client is registered |
| `vault_vpn_portal_oauth2_client_secret` | `OAUTH2_CLIENT_SECRET` in `website_secrets` of `vpn_portal` | `vpn_portal` is enabled | Client secret shown by auth when the client is registered |
| `vault_team_oauth2_client_secret` | `OAUTH2_CLIENT_SECRET` in `website_secrets` of `team` | Optional: `team` is enabled and calls protected services | Client secret shown by auth when the client is registered |
| `vault_webhooks_oauth2_client_secret` | `OAUTH2_CLIENT_SECRET` in `website_secrets` of `webhooks` | Optional: `webhooks` forwards events to mailler | Client secret shown by auth when the client is registered |
| `vault_vpn_portal_openvpn_oauth2_client_secret` | `OPENVPN_OAUTH2_CLIENT_SECRET` of `vpn_portal_openvpn` | `vpn_portal_openvpn` is enabled | Client secret shown by auth when the client is registered |
| `vault_auth_jwks_encryption_key` | `JWKS_ENCRYPTION_KEY` in `website_secrets` of `auth` | `auth` is enabled (example inventory) | `openssl rand -base64 32` (base64 of 32 bytes: AES-256-GCM key). Losing it makes the stored signing keys and MFA secrets unreadable |
| `vault_smtp_password` | `SMTP_PASSWORD` in `website_secrets` of `auth` (optional) | Optional: mail goes through SMTP (example inventory) | Password of the SMTP account |
| `vault_auth_mailler_client_secret` | `MAILLER_CLIENT_SECRET` in `website_secrets` of `auth` | `auth` sends its mail through mailler (the example sends it through SMTP instead) | Secret of the auth client registered in mailler |
| `vault_openai_api_key` | `OPENAI_API_KEY` in `website_secrets` of `backend, asterisk, internal, knowledge, team` | `backend` is enabled (example inventory); also `asterisk`, `internal`, `knowledge`, `team` | API key of the OpenAI account |
| `vault_apt_server_session_secret` | `SESSION_SECRET` in `website_secrets` of `apt_server` | `apt_server` is enabled | `openssl rand -hex 32` |
| `vault_apt_server_webhook_secret` | `WEBHOOK_SECRET` in `website_secrets` of `apt_server` | `apt_server` is enabled | `openssl rand -hex 32` |
| `vault_apt_server_mailler_client_secret` | `MAILLER_CLIENT_SECRET` in `website_secrets` of `apt_server` | `apt_server` is enabled | Secret of the apt_server client registered in mailler |
| `vault_internal_secret_key` | `SECRET_KEY` in `website_secrets` of `internal` | `internal` is enabled | `openssl rand -hex 32` |
| `vault_stripe_secret_key` | `STRIPE_SECRET_KEY` in `website_secrets` of `billing` | `billing` is enabled | Secret (or restricted) key of the Stripe account |
| `vault_stripe_webhook_secret` | `STRIPE_WEBHOOK_SECRET` in `website_secrets` of `billing` | `billing` is enabled | Signing secret of the Stripe webhook endpoint (`whsec_...`) |
| `vault_mailler_brevo_api_key` | `BREVO_API_KEY` in `website_secrets` of `mailler` | `mailler` is enabled | API key of the Brevo account |
| `vault_mailler_webhook_hmac_secret` | `WEBHOOK_HMAC_SECRET` in `website_secrets` of `mailler` | `mailler` is enabled | `openssl rand -hex 32` |
| `vault_mailler_sendgrid_api_key` | `SENDGRID_API_KEY` in `website_secrets` of `mailler` (optional) | Optional: SendGrid provider | API key of the SendGrid account |
| `vault_mailler_ses_access_key` | `SES_ACCESS_KEY` in `website_secrets` of `mailler` (optional) | Optional: SES provider (also needs `SES_REGION`) | Access key id of the AWS SES user |
| `vault_mailler_ses_secret_key` | `SES_SECRET_KEY` in `website_secrets` of `mailler` (optional) | Optional: SES provider | Secret access key of the AWS SES user |
| `vault_mailler_protonmail_password` | `PROTONMAIL_PASSWORD` in `website_secrets` of `mailler` (optional) | Optional: Proton Mail Bridge provider (also needs user and port) | Bridge password shown by `protonmail-bridge` |
| `vault_team_anthropic_api_key` | `ANTHROPIC_API_KEY` in `website_secrets` of `team` (optional) | Optional: `team` uses Anthropic models | API key of the Anthropic account |
| `vault_team_github_token` | `GITHUB_TOKEN` in `website_secrets` of `team` (optional) | Optional: `team` reads GitHub | Token of a GitHub account or app |
| `vault_vpn_portal_stepca_password` | `STEPCA_PROVISIONER_PASSWORD` in `website_secrets` of `vpn_portal` and `step_ca_vpn_portal_password` | `vpn_portal` is enabled | `openssl rand -base64 32` (same value on both sides) |
| `vault_users_deploy_password_hash` | `users_deploy_password_hash` (users role) | Only with `users_deploy_sudo: password` | `mkpasswd --method=sha-512` (a crypt hash, not the password) |
| `vault_redis_password` | `redis_password` (redis role) and `website_redis_password` | Optional: Redis listens on TCP or is shared with other hosts | `openssl rand -hex 32` |
| `vault_geoip_account_id` | `geoip_account_id` (geoip role) | The geoip role is enabled | MaxMind account page |
| `vault_geoip_license_key` | `geoip_license_key` (geoip role) | The geoip role is enabled | MaxMind account page (License keys) |
| `vault_geoip_proxy_user_password` | `geoip_proxy_user_password` (geoip role) | Optional: downloads go through an authenticated proxy | Given by the proxy; the variable holds `user:password` |
| `vault_asterisk_trunk_password` | `asterisk_trunk_password` (asterisk role) | The SIP trunk of the asterisk role is enabled | SIP account password of the provider |
| `vault_step_ca_password` | `step_ca_password` (step_ca role) | The step_ca role is enabled | `openssl rand -base64 32` |
| `vault_openvpn_stepca_password` | `openvpn_stepca_password` (openvpn role) and `password` of the matching provisioner of `step_ca_provisioners` | The openvpn role uses the step-ca backend | `openssl rand -base64 32` (same value on both sides) |
| `vault_step_ca_postgres_password` | `step_ca_postgres_password` (step_ca role) | Optional: step-ca reaches PostgreSQL with a password instead of peer authentication | `openssl rand -hex 32` |
| `vault_aws_route53_access_key_id` | `website_aws_route53_access_key_id` | Wildcard certificates through Route 53 | IAM user limited to the hosted zone |
| `vault_aws_route53_secret_access_key` | `website_aws_route53_secret_access_key` | Wildcard certificates through Route 53 | Secret access key of the same IAM user |
| `vault_aws_ses_access_key_id` | `website_aws_ses_access_key_id` | Optional: SES/SNS notifications configured by the role | IAM user limited to SES and SNS |
| `vault_aws_ses_secret_access_key` | `website_aws_ses_secret_access_key` | Optional: SES/SNS notifications configured by the role | Secret access key of the same IAM user |

The roles take their secrets from plain variables that are empty by default
(`redis_password`, `geoip_license_key`, `step_ca_password`, ...). Set them from
the vault, as for `website_repo_token` below, for instance
`redis_password: "{{ vault_redis_password }}"`; no role has a secret built in.

## Other secrets

| Secret | Variable | Notes |
| --- | --- | --- |
| Token to clone a private repository | `website_repo_token` | Used in an HTTPS URL for the clone only; the task output is hidden. |
| Route 53 access for wildcard certificates | `website_aws_route53_access_key_id`, `website_aws_route53_secret_access_key` | Written to `/root/.aws/credentials` (mode 0600). |
| AWS access for SES notifications | `website_aws_ses_access_key_id`, `website_aws_ses_secret_access_key` | Passed to the AWS CLI through its environment, not written to disk. |
| Role-specific secrets | `step_ca_password`, `users_deploy_password_hash`, ... | See the page of each role and [Variables of the vault](#variables-of-the-vault). |

Reference them from the vault in the same way:

```yaml
website_repo_token: "{{ vault_website_repo_token | default('') }}"
```

## What not to do

- Do not put a secret in `env_vars`: it would be written, in clear text, to the
  environment file.
- Do not commit `vault.yml` unencrypted or `.vault_pass`.
- Do not reuse a value between environments; the vault is per infrastructure
  repository.
