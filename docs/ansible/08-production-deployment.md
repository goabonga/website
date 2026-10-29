# Production deployment

Production is deployed by two GitHub workflows, not by hand. A deployment is a
pull request: it shows which releases will ship and what Ansible would change,
a reviewer approves it, and the merge applies it. `main` then records the
deployment, so its history is the deployment journal.

## The environment

Everything that describes production is in `deploy/production/`:

| File | Role |
| --- | --- |
| `deploy.yml` | `version`, the number of the last deployment, and `playbooks`, the playbooks run in order (`site`, `apps`). |
| `ansible.cfg` | Uses the collection installed from this checkout into `collections/`. |
| `inventory/hosts.yml` | One host. Its address and account come from the environment variables `DEPLOY_HOST` and `DEPLOY_USER`, so no address is committed. |
| `inventory/group_vars/all/main.yml`, `apps.yml` | The settings of the environment: domain, enabled applications, overrides. |
| `inventory/group_vars/all/pins.yml` | The release of each enabled application. Written by the workflow. |
| `inventory/group_vars/all/vault.yml` | The secrets, encrypted with `ansible-vault` and committed encrypted. Start from `ansible/examples/inventory/group_vars/all/vault.yml.example`: the variables to define depend on the enabled applications and roles ([Secrets](03-secrets.md#variables-of-the-vault)). |

The values of `main.yml` and `apps.yml` are the real ones of the platform, not
examples; [what they configure](#what-the-inventory-configures) is listed
below. Change them in a pull request like any other deployment. The host must
already be bootstrapped (`bootstrap` playbook, run once by hand).

## Files fetched to the controller

The playbooks fetch a few files from the host to the machine that runs them. By default they go to the `exports` directory next to the `inventory` directory of the environment (`deploy/production/exports/` for production), and the directory is ignored by Git:

| Path | Content | Setting |
| --- | --- | --- |
| `exports/step-ca/root_ca.crt` | Root certificate of the authority | `step_ca_export_dir` |
| `exports/step-ca/<provisioner>-provisioner.pub` | Public key of the VPN portal provisioner | `step_ca_export_dir` |
| `exports/openvpn-clients/<name>.ovpn` | VPN client profiles, with the private key of each client | `openvpn_clients_export_dir` |

The profiles embed private keys: keep the directory out of Git and out of shared storage. The files are fetched again by every run, so the host stays the source of truth.

## What the inventory configures

The inventory describes the platform that ran before the collection: the
settings that differ from the role defaults and from the catalog were carried
over, and nothing else. A value that the vault holds is a reference
(`{{ vault_... }}`), never the value.

**`main.yml`**

| Area | Configured |
| --- | --- |
| Zone | `website_domain` is `goabonga.com`; every application is served under its default label (`auth`, `api`, `ua`, `apt`, `vpn`, ... and `.internal` for the internal ones). |
| Certificates | Contact address of Let's Encrypt, nginx reloaded after each renewal, wildcard certificates of `auth` and `knowledge` through Route 53 (credentials from the vault). |
| Platform tenant of auth | Slug `goabonga`, display name `GOABONGA`. The Swagger UI client holds the `*` scope, so that `/docs` calls the admin API with the scopes of the signed-in administrator. |
| Host | Time zone `Europe/Paris`, locale `fr_FR.UTF-8`. The prompt and the tmux configuration of the previous deployment are kept: `common_bash_prompt_enabled` and `common_tmux_enabled` are off. |
| Roles | On top of the default ones: `dnsmasq`, `step_ca`, `geoip`, `openvpn`, `asterisk` and `protonmail_bridge`. `users` and `security` belong to `bootstrap`. |
| Redis, PostgreSQL | Unix sockets only (`redis_port` and `postgres_port` are 0), pgvector enabled, PostgreSQL in the time zone of the host, and the `peer` map that lets the step-ca account reach its database. |
| nginx | The catch-all virtual host of the previous deployment: it listens on the addresses of the host, serves the challenge of the customer domains from `/var/www/certbot` and redirects to the host name. |
| fail2ban | Bans with iptables, the nginx jails are on; the VPN network is never banned. |
| step-ca | ACME endpoint behind nginx, certificates in PostgreSQL, revocation list, provisioner of the VPN portal, signing key of the repository where the previous deployment put it. |
| OpenVPN | Certificates from step-ca, step-ca reachable through the VPN, the seven clients with their fixed addresses. |
| Internal applications | They listen on the address of the VPN server and only answer the VPN network. |
| Mail | SMTP host of auth, SES region and Proton Mail Bridge of mailler, CNAME target `apps.<zone>` of the custom domain service. |

**`apps.yml`**

| Area | Configured |
| --- | --- |
| Applications | The 16 applications, in an order that suits a first run (`custom_domain`, `knowledge`, `mailler`, `billing` first). |
| OAuth2 clients | `website_oauth2_clients` points to the identifiers kept in the vault. |
| Secrets | `website_secrets` maps every secret of the catalog to its vault variable. |
| Overrides | Identity and legal notice of the frontend, `security.txt`, names and docs of the applications that had them, tenant issuers of `knowledge` and `apt_server` (trusted by `billing`), allowed networks of the robot API, workspace and GitHub owner of `team`, prompt and greeting of the Asterisk bot. |
| Knowledge | Registered as a client of `custom_domain`, `mailler` and `billing`. Its SaaS application identifier comes from the vault once billing has created it: a second run is needed ([Onboarding a SaaS application](07-saas-onboarding.md)). |

Not configured, by choice or because there is nothing to read it from:

- The SIP trunk of Asterisk: its account name is not committed, so
  `asterisk_trunk_enabled` stays off until it is set with the account (the
  password is `vault_asterisk_trunk_password`).
- The host name virtual host of nginx (the host name is only used by the
  redirect of the catch-all one) and the accounts of `users`: they identify the
  host.
- The debug logging and `DEBUG` flags of the previous deployment.
- The Stripe publishable key (`website_billing_stripe_publishable_key`) and the
  products of billing.
- The OAuth2 clients that the example vault has no variable for (see
  [Variables of the vault](03-secrets.md#variables-of-the-vault)): Swagger UI
  clients, the web client of `internal` and `knowledge`, the mailler clients of
  `auth` and `apt_server`.

## Versions

| Component | What it versions | Tag |
| --- | --- | --- |
| `ansible` | The collection: roles, metadata | `ansible-vX.Y.Z` |
| `playbook-bootstrap`, `playbook-site`, `playbook-apps` | One playbook each; the version is the `website_playbook_version` variable of the play | `playbook-<name>-vX.Y.Z` |
| each application | The application | `<app>-vX.Y.Z` |
| `deploy-production` | What is deployed to production | `deploy-production-vX.Y.Z` |

`deploy-production` is the only component that is not a library. It depends on
all the others, so a release of any of them makes production owe a
deployment, and only the deploy workflows bump it, after a successful apply:
the `release-bump` job of `ci` leaves every `deploy-*` component out. The
`upstream-notes` plugin of multicz writes the commits of the applications, of
the collection and of the playbooks that a deployment shipped into its
changelog and release notes.

The collection is installed from this checkout, not from a release: a
deployment runs the exact roles and playbooks of the commit that was reviewed.
Applications are deployed from their own tags through `website_apps_pins`
([Deploying applications](05-deploying-apps.md)).

## The cycle

1. **Plan** (`deploy-plan`). When `ci` has finished on `main` and
   `deploy-production` is pending, the workflow resets `deploy/production` to
   `main`, writes the pins (the last tag of each enabled application, through
   `scripts/deploy-pins.sh`) and bumps `deploy-production`. It then runs every
   playbook of `deploy.yml` in check mode against the host.
2. **Proposal.** If the pins changed or check mode predicts changes, it opens
   the pull request `deploy/production-<version>` into `deploy/production`.
   The description lists the releases that change and the names of the tasks
   that would change. With no drift, nothing is proposed.
3. **Approval.** The reviewers merge the pull request into `deploy/production`.
4. **Apply** (`deploy-apply`). The merge starts the workflow in the
   `production` GitHub Environment, which waits for its required reviewers.
   It then runs the playbooks, tags `deploy-production-v<version>`, publishes
   the release and lands the deployment commit on `main`.

If the apply fails, nothing is tagged and `main` is untouched: production stays
pending and the next plan proposes the next version. If the apply succeeds but
`main` cannot be updated, the job fails with the command to run by hand.

## What check mode cannot see

Tasks that run commands (`command`, `shell`, `uv sync`, builds) are skipped in
check mode, so what they would change is invisible to it. The pins cover part
of that gap: a new release of an application is drift whatever check mode says.
A clean check is therefore not a proof that nothing changes. The exception is
`auth`: its `bootstrap`, `catalog sync` and `tenant-roles sync` commands run in
check mode too, with `--dry-run`, so the plan lists the scopes, roles and rows they would create (once
the migrations are applied; before that their failure is ignored).

## Setting up GitHub

| Where | What |
| --- | --- |
| Environment `production-plan` | Secrets `DEPLOY_SSH_PRIVATE_KEY`, `DEPLOY_SSH_KNOWN_HOSTS`, `ANSIBLE_VAULT_PASSWORD`; variables `DEPLOY_HOST`, `DEPLOY_USER`. Use a read-only identity: its own key and sudo rules limited to what check mode needs. No required reviewers. |
| Environment `production` | The same secrets and variables with the identity that may apply. Required reviewers. |
| Branch `deploy/production` | Protected: a pull request and one approving review from a code owner (`deploy/**` is owned in `CODEOWNERS`). |
| Repository secrets | `RELEASE_PAT`, whose owner may push to `main` and `deploy/*` (bypass actor of the rulesets). `GPG_PRIVATE_KEY` and `GPG_PASSPHRASE` to sign the deployment commits (optional). |
| Repository variable `DEPLOY_PLAN_ARTIFACT` | `true` to attach the full check output to the run. Leave it unset on a public repository: the diff can contain the content of rendered files. |

Merge the deployment pull requests with a merge commit or a rebase, never a
squash: the pins commit and the bump commit must stay as they are.
