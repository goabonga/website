# Ansible

The `goabonga.website` collection provisions hosts and deploys the platform
applications. It lives in the `ansible/` directory of the monorepo and is
installed from Git; it is not published to Ansible Galaxy.

## Contents

- **Roles** for the base infrastructure (users, SSH hardening, packages,
  PostgreSQL, Redis, nginx, certbot, fail2ban, DNS, a private CA, OpenVPN,
  Asterisk, ...). See [Roles](roles/index.md).
- **`python_app`**, the role that deploys the applications of this repository
  from a catalog of components. See [python_app](roles/python_app.md) and
  [Deploying applications](05-deploying-apps.md).
- **Three playbooks**: `bootstrap`, `site` and `apps`. See
  [Playbooks](06-playbooks.md).
- **A production deployment pipeline**: drift check, pull request and apply
  from GitHub Actions. See [Production deployment](08-production-deployment.md).
- **An example project** in `ansible/examples/`: inventory, variables, vault
  template and `ansible.cfg` to copy as the start of an infrastructure
  repository.

## How the applications are deployed

Applications are not published to PyPI and no Debian package is built. A
deployment checks the monorepo out on the host, installs one workspace member
with `uv sync --frozen --no-dev --package <name>` into its own virtualenv,
writes the environment file and the encrypted credentials, and runs the
service under systemd. Each application can be pinned to one of its releases
(`<app>-vX.Y.Z` tags) independently of the others.

## Reading order

| Page | Content |
| --- | --- |
| [Getting started](01-getting-started.md) | From an empty project to a running host. |
| [Configuration](02-configuration.md) | Where variables live and how they layer. |
| [Secrets](03-secrets.md) | The vault, and how applications receive their secrets. |
| [Tags](04-tags.md) | Running a part of a playbook. |
| [Deploying applications](05-deploying-apps.md) | The catalog, the overrides, releases and rollbacks. |
| [Playbooks](06-playbooks.md) | What `bootstrap`, `site` and `apps` run, and their switches. |
| [Onboarding a SaaS application](07-saas-onboarding.md) | Registering the clients of custom-domain, mailler and billing. |
| [Roles](roles/index.md) | One page per role, with every variable. |

## Requirements

- On the controller: `ansible-core` 2.16 or later, and the collections the
  collection depends on (`ansible.posix`, `community.general`,
  `community.postgresql`, `community.crypto`), which `ansible-galaxy` installs
  with it.
- On the hosts: Debian 12 or 13, or Ubuntu 22.04 or 24.04, reachable over SSH.
