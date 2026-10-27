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

Edit the values of `main.yml` and `apps.yml` for your domain and applications
before the first deployment; they ship with documentation values. The host must
already be bootstrapped (`bootstrap` playbook, run once by hand).

## Files fetched to the controller

The playbooks fetch a few files from the host to the machine that runs them. By default they go to the `exports` directory next to the `inventory` directory of the environment (`deploy/production/exports/` for production), and the directory is ignored by Git:

| Path | Content | Setting |
| --- | --- | --- |
| `exports/step-ca/root_ca.crt` | Root certificate of the authority | `step_ca_export_dir` |
| `exports/step-ca/<provisioner>-provisioner.pub` | Public key of the VPN portal provisioner | `step_ca_export_dir` |
| `exports/openvpn-clients/<name>.ovpn` | VPN client profiles, with the private key of each client | `openvpn_clients_export_dir` |

The profiles embed private keys: keep the directory out of Git and out of shared storage. The files are fetched again by every run, so the host stays the source of truth.

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
the release job of `ci` leaves every `deploy-*` component out. The
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
`auth`: its `bootstrap` and `catalog sync` commands run in check mode too, with
`--dry-run`, so the plan lists the scopes, roles and rows they would create (once
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
