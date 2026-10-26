# Background maintenance and operations scripts

The periodic jobs that keep the database small, the provisioning of custom
domains, a one-off data backfill and the command line scripts used to
bootstrap and administer a deployment.

## What it does

### Cleanup tasks

`auth.tasks.cleanup` holds one Celery task per kind of expiring record. They
use the synchronous session helper and the SQL of
`auth.db.repositories.cleanup`, and each returns a dictionary of counters.

- tokens: expired or revoked access and refresh tokens;
- authorization codes, device codes and pushed authorization requests that
  passed their expiry;
- e-mail verification codes, password reset tokens and MFA e-mail codes;
- user sessions that expired or were revoked;
- personal access tokens, after a grace period (30 days after expiry, 90 days
  after revocation);
- avatar files in the upload directory that no profile references any more
  (switch off with `ORPHAN_AVATAR_CLEANUP_ENABLED`);
- users whose primary address stayed unverified for more than
  `UNVERIFIED_USER_EXPIRY_DAYS` days, together with their avatar. The cascade
  removes their related records.

### Custom domain provisioning

An organisation can serve the login pages on its own domain. The tasks of
`auth.tasks.custom_domain` run on the worker host:

- `verify_custom_domain_dns` validates the domain name, checks that a CNAME
  points to `CUSTOM_DOMAIN_CNAME_TARGET`, records the status of the tenant
  (`dns_verifying`, `pending`, `dns_verified`, `failed`) and, once the DNS is
  correct, queues `provision_custom_domain_ssl`. A malformed domain or a missing
  target fails at once. While the DNS is not ready the task retries with an
  exponential back-off (5, 10, then 20 minutes) and then leaves the domain
  `pending` for a manual check;
- `provision_custom_domain_ssl` (status `ssl_provisioning`) writes an HTTP-only
  nginx server block from a template (`CUSTOM_DOMAIN_NGINX_TEMPLATE` overrides
  the built-in one) into `CUSTOM_DOMAIN_NGINX_SITES_DIR`, reloads nginx, obtains
  a certificate with certbot when `CUSTOM_DOMAIN_CERTBOT_ENABLED` is set,
  rewrites the block with TLS and the upstream socket, reloads nginx again and
  marks the domain `active`. Any failed step marks it `failed` with the error;
- `check_pending_custom_domains` runs every five minutes from the beat schedule
  and queues `verify_custom_domain_dns` for the active tenants whose domain is
  still `pending` or `dns_verifying`, skipping those checked less than
  `CUSTOM_DOMAIN_DNS_CHECK_INTERVAL_MINUTES` ago;
- `remove_custom_domain_config` deletes the server block and reloads nginx when
  an organisation drops its domain.

The tasks run `nginx` and `certbot` through `sudo`; the sudoers entries and the
writable paths belong to the deployment.

### Pairwise subject backfill

`backfill_pairwise_subjects` (on demand, no schedule) creates the pairwise
subject of every (user, tenant) pair found in the access tokens, using the
platform tenant for clients without a tenant. It reports `created`, `existing`
and `total`, or `error: no_platform_tenant` when no platform tenant exists.

### Tasks

| Task | Beat schedule |
| --- | --- |
| `backfill_pairwise_subjects` | on demand |
| `check_pending_custom_domains` | `check-pending-custom-domains`, cron `*/5 * * * *` |
| `cleanup_expired_authorization_codes` | `cleanup-expired-authorization-codes`, cron `*/15 * * * *` |
| `cleanup_expired_device_codes` | `cleanup-expired-device-codes`, cron `*/30 * * * *` |
| `cleanup_expired_mfa_email_codes` | `cleanup-expired-mfa-email-codes`, cron `*/30 * * * *` |
| `cleanup_expired_par_requests` | `cleanup-expired-par-requests`, cron `*/15 * * * *` |
| `cleanup_expired_password_reset_tokens` | `cleanup-expired-password-reset-tokens`, cron `0 * * * *` |
| `cleanup_expired_pats` | `cleanup-expired-pats`, cron `0 3 * * *` |
| `cleanup_expired_sessions` | `cleanup-expired-sessions`, cron `0 0 * * *` |
| `cleanup_expired_tokens` | `cleanup-expired-tokens`, cron `0 * * * *` |
| `cleanup_expired_verification_codes` | `cleanup-expired-verification-codes`, cron `0 * * * *` |
| `cleanup_orphaned_avatars` | `cleanup-orphaned-avatars`, cron `0 */12 * * *` |
| `cleanup_unverified_users` | `cleanup-unverified-users`, cron `30 */12 * * *` |
| `provision_custom_domain_ssl` | on demand |
| `remove_custom_domain_config` | on demand |
| `verify_custom_domain_dns` | on demand |

### Operations scripts

The scripts of `apps/auth/scripts/` open their own database session, so they
only need `DATABASE_URL` (and `JWKS_ENCRYPTION_KEY` for the keys):

| Script | Purpose |
| --- | --- |
| `create_user.py` | create a user (`--email`, `--password`, `--verified`, profile fields, `--json`); refuses an address that exists |
| `promote_user.py` | assign (`--role`), remove (`--role --remove`) or show (`--show`) the roles of a user, or list the roles (`--list-roles`) |
| `create_oauth2_client.py` | register an OAuth2 client and print its credentials |
| `generate_jwks.py` | generate a signing key (`--key-size`, `--no-activate`) |

```bash
uv run --package auth python apps/auth/scripts/create_user.py --help
```

## Endpoints

This feature adds no HTTP endpoint.

## Settings

| Variable | Default | Description |
| --- | --- | --- |
| `CUSTOM_DOMAIN_CNAME_TARGET` | (empty) | CNAME target that organisations point their domain to (a host name of the service) |
| `CUSTOM_DOMAIN_NGINX_SITES_DIR` | `/etc/nginx/sites-enabled` | Nginx sites directory |
| `CUSTOM_DOMAIN_NGINX_TEMPLATE` | (empty) | Path to nginx template (empty = use built-in) |
| `CUSTOM_DOMAIN_NGINX_IPV4` | (empty) | IPv4 address nginx listens on for custom domains |
| `CUSTOM_DOMAIN_NGINX_IPV6` | (empty) | IPv6 address nginx listens on for custom domains |
| `CUSTOM_DOMAIN_UPSTREAM_SOCKET` | `/run/auth/auth.sock` | Unix socket for upstream |
| `CUSTOM_DOMAIN_CERTBOT_ENABLED` | `True` | Enable automatic SSL via certbot |
| `CUSTOM_DOMAIN_CERTBOT_EMAIL` | (empty) | Email for certbot notifications |
| `CUSTOM_DOMAIN_DNS_CHECK_INTERVAL_MINUTES` | `5` | How often to check pending domains |
| `UNVERIFIED_USER_EXPIRY_DAYS` | `3` | Days before unverified users are deleted |
| `ORPHAN_AVATAR_CLEANUP_ENABLED` | `True` | Enable/disable orphan avatar cleanup |

## Data model

This feature adds no table.

The jobs work on the tables of the earlier features. The custom domain status
is stored on the tenant (`custom_domain_status`, the verification and
certificate dates and the last error).

## Tests

- pytest: 3 new test modules and 1 existing modules extended.
  New modules: `tests/test_backfill_pairwise.py`, `tests/test_tasks_cleanup.py`, `tests/test_tasks_custom_domain.py`.
  Extended: `tests/test_celery_app.py`.
- behave: `features/maintenance.feature` with the scenarios *Expired and revoked sessions are purged*, *Accounts that never verified their address are purged*, *The pairwise backfill needs a platform tenant*, *The pairwise backfill has nothing to do without tokens*, *The beat scheduler knows every maintenance job*, *Custom domain names are validated*, *A custom domain pointing to the right target is verified*, *A malformed custom domain is rejected*, *A missing CNAME target fails the verification*, *The create_user script bootstraps an account*, *The create_user script refuses an existing address*, *The promote_user script refuses an unknown user*.

The behave scenarios call the task functions directly against the in-process
database, replace the DNS lookup and the certificate steps of the custom domain
tasks by fakes (nginx and certbot are never run), and execute the scripts
in process with their arguments, capturing the output and the exit code.
