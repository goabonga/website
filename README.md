# website

[![CI](https://github.com/goabonga/website/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/goabonga/website/actions/workflows/ci.yml)
[![Codecov](https://img.shields.io/codecov/c/github/goabonga/website?logo=codecov)](https://codecov.io/gh/goabonga/website)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](https://github.com/goabonga/website/blob/main/LICENSE)
[![Python](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://www.python.org/downloads/)
[![uv](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/uv/main/assets/badge/v0.json)](https://github.com/astral-sh/uv)

Monorepo of the platform services and the Ansible collection that deploys them.

The repository contains sixteen Python applications (FastAPI services) in
`apps/`, managed as members of a single
[uv workspace](https://docs.astral.sh/uv/concepts/projects/workspaces/), the
`goabonga.website` Ansible collection in `ansible/` that provisions hosts and
deploys the applications, and the documentation site in `docs/`. Nothing is
published to PyPI, Debian or Ansible Galaxy: applications are deployed from
this repository by Ansible.

## Packages

Every package owns its version, changelog and git tag.

| Package | Role | Documentation | Tag |
| --- | --- | --- | --- |
| [`analytics`](apps/analytics) | Privacy-friendly analytics service. | [docs](docs/apps/analytics/index.md) | `analytics-v<version>` |
| [`apt-server`](apps/apt-server) | FastAPI microservice serving a signed APT repository with per-package access control. | [docs](docs/apps/apt-server/index.md) | `apt-server-v<version>` |
| [`asterisk`](apps/asterisk) | Voice bot bridging Asterisk AudioSocket calls to the OpenAI Realtime API. | [docs](docs/apps/asterisk/index.md) | `asterisk-v<version>` |
| [`auth`](apps/auth) | Centralized OIDC/OAuth2 authentication service. | [docs](docs/apps/auth/index.md) | `auth-v<version>` |
| [`backend`](apps/backend) | Main API service of the platform. | [docs](docs/apps/backend/index.md) | `backend-v<version>` |
| [`billing`](apps/billing) | Multi-SaaS Stripe billing platform API. | [docs](docs/apps/billing/index.md) | `billing-v<version>` |
| [`custom-domain`](apps/custom-domain) | Centralized custom domain management with DNS verification and SSL provisioning. | [docs](docs/apps/custom-domain/index.md) | `custom-domain-v<version>` |
| [`frontend`](apps/frontend) | Frontend application server (FastAPI) serving the website single page application. | [docs](docs/apps/frontend/index.md) | `frontend-v<version>` |
| [`internal`](apps/internal) | Internal admin dashboard for managing platform services. | [docs](docs/apps/internal/index.md) | `internal-v<version>` |
| [`knowledge`](apps/knowledge) | Vector storage and semantic search SaaS for AI agents, LLMs and RAG applications. | [docs](docs/apps/knowledge/index.md) | `knowledge-v<version>` |
| [`mailler`](apps/mailler) | Internal email sending service with multi-provider support, campaigns and inbound processing. | [docs](docs/apps/mailler/index.md) | `mailler-v<version>` |
| [`mta-sts`](apps/mta-sts) | Minimal FastAPI service serving the MTA-STS policy (RFC 8461). | [docs](docs/apps/mta-sts/index.md) | `mta-sts-v<version>` |
| [`reachy-mini-api`](apps/reachy-mini-api) | Internal API for the Reachy Mini robot: reports, status and a WebSocket channel. | [docs](docs/apps/reachy-mini-api/index.md) | `reachy-mini-api-v<version>` |
| [`team`](apps/team) | Multi-agent orchestration platform: AI agents, workflows, tasks and memory behind a REST API. | [docs](docs/apps/team/index.md) | `team-v<version>` |
| [`vpn-portal`](apps/vpn-portal) | Zero-Trust VPN authentication and certificate issuance service. | [docs](docs/apps/vpn-portal/index.md) | `vpn-portal-v<version>` |
| [`webhooks`](apps/webhooks) | FastAPI gateway receiving provider webhooks and forwarding them to internal services. | [docs](docs/apps/webhooks/index.md) | `webhooks-v<version>` |
| [`ansible`](ansible) | Ansible collection `goabonga.website`: roles that provision hosts and deploy the applications. | [docs](docs/ansible/index.md) | `ansible-v<version>` |
| [`playbook-bootstrap`](ansible/playbooks/bootstrap.yml) | First run on a fresh host: deploy account and SSH hardening. | [docs](docs/ansible/06-playbooks.md) | `playbook-bootstrap-v<version>` |
| [`playbook-site`](ansible/playbooks/site.yml) | Base infrastructure of the platform. | [docs](docs/ansible/06-playbooks.md) | `playbook-site-v<version>` |
| [`playbook-apps`](ansible/playbooks/apps.yml) | Deployment of the enabled applications. | [docs](docs/ansible/06-playbooks.md) | `playbook-apps-v<version>` |
| [`deploy-production`](deploy/production) | What is deployed to production, recorded by the deploy workflows after each apply. | [docs](docs/ansible/08-production-deployment.md) | `deploy-production-v<version>` |

## Documentation

The documentation site is built with [Zensical](https://zensical.org/) from
`docs/` and published from `main` to GitHub Pages:
<https://goabonga.github.io/website/>.

## Requirements

- Python 3.11+
- [uv](https://docs.astral.sh/uv/) for environment management

## Getting started

```bash
git clone https://github.com/goabonga/website.git
cd website
uv sync
uv run pre-commit install --install-hooks -t pre-commit -t commit-msg
```

Run the tests of one application (replace `auth` with any directory of
`apps/`); the suites mock the database, Redis and SMTP, so they need no
infrastructure:

```bash
uv run --package auth --group dev pytest apps/auth
uv run --package auth --group dev behave apps/auth/features
```

Lint the workspace and build the documentation:

```bash
uv run ruff check .
uv run ruff format --check .
uv sync --only-group doc && uv run zensical build --clean
```

## Versioning and release

Versions are bumped from
[Conventional Commits](https://www.conventionalcommits.org/) by
[multicz](https://github.com/goabonga/multicz), configured in `multicz.toml`.
On every push to `main`, once all CI gates pass, CI computes the bump of each
component, writes its changelog, creates the release commit and tags (GPG-signed when the key is configured), then
publishes a GitHub Release per bumped component. The `ansible` release also
carries the built collection tarball, and the documentation is deployed to
GitHub Pages. Maintainers do not bump versions or edit changelogs by hand.

Tags are named `<component>-v<version>`, for example `auth-v1.2.0`,
`ansible-v1.0.0` or `playbook-site-v1.0.0`. The playbooks depend on the
`ansible` component, so a collection release also releases them.

`deploy-production` is the exception: the release job leaves it out, and only the
deploy workflows bump it, after a deployment has been applied. A `deploy-plan` run
opens a pull request when production owes a deployment and `deploy-apply` applies it
once it is merged and approved. See
[Production deployment](docs/ansible/08-production-deployment.md).

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for the workflow, the commit-message
convention and scopes, and the test and lint expectations. By participating
you agree to the [Code of Conduct](CODE_OF_CONDUCT.md).

Security issues: please follow the disclosure process in
[SECURITY.md](SECURITY.md).

## License

Distributed under the [MIT License](LICENSE).
