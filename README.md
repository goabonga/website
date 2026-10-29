<h1 align="center">
  <img src="docs/website.svg" alt="website" width="120" /><br/>
  website
</h1>

<p align="center">
  <em>Monorepo of the platform services and the Ansible collection that deploys them.</em>
</p>

<p align="center">
  <a href="https://github.com/goabonga/website/actions/workflows/ci.yml"><img src="https://github.com/goabonga/website/actions/workflows/ci.yml/badge.svg?branch=main" alt="CI"/></a>
  <a href="https://codecov.io/gh/goabonga/website"><img src="https://img.shields.io/codecov/c/github/goabonga/website?logo=codecov" alt="Codecov"/></a>
  <a href="https://github.com/goabonga/website/blob/main/LICENSE"><img src="https://img.shields.io/badge/License-MIT-blue.svg" alt="License: MIT"/></a>
  <a href="https://www.python.org/downloads/"><img src="https://img.shields.io/badge/python-3.11%2B-blue.svg" alt="Python"/></a>
  <a href="https://github.com/astral-sh/uv"><img src="https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/uv/main/assets/badge/v0.json" alt="uv"/></a>
</p>

The repository contains sixteen Python applications (FastAPI services) in
`apps/`, managed as members of a single
[uv workspace](https://docs.astral.sh/uv/concepts/projects/workspaces/), the
`goabonga.website` Ansible collection in `ansible/` that provisions hosts and
deploys the applications, and the documentation site in `docs/`. Nothing is
published to PyPI, Debian or Ansible Galaxy: applications are deployed from
this repository by Ansible.

## Packages

Every package owns its version, changelog and git tag. The Tag column is
rewritten by `multicz` in the release commit of the package.

| Package | Role | Documentation | Tag |
| --- | --- | --- | --- |
| [`analytics`](apps/analytics) | Privacy-friendly analytics service. | [docs](docs/apps/analytics/index.md) | <code>analytics-v<!-- v:analytics -->0.0.0<!-- /v --></code> |
| [`apt-server`](apps/apt-server) | FastAPI microservice serving a signed APT repository with per-package access control. | [docs](docs/apps/apt-server/index.md) | <code>apt-server-v<!-- v:apt-server -->0.0.0<!-- /v --></code> |
| [`asterisk`](apps/asterisk) | Voice bot bridging Asterisk AudioSocket calls to the OpenAI Realtime API. | [docs](docs/apps/asterisk/index.md) | <code>asterisk-v<!-- v:asterisk -->0.0.0<!-- /v --></code> |
| [`auth`](apps/auth) | Centralized OIDC/OAuth2 authentication service. | [docs](docs/apps/auth/index.md) | <code>auth-v<!-- v:auth -->0.0.0<!-- /v --></code> |
| [`backend`](apps/backend) | Main API service of the platform. | [docs](docs/apps/backend/index.md) | <code>backend-v<!-- v:backend -->0.0.0<!-- /v --></code> |
| [`billing`](apps/billing) | Multi-SaaS Stripe billing platform API. | [docs](docs/apps/billing/index.md) | <code>billing-v<!-- v:billing -->0.0.0<!-- /v --></code> |
| [`custom-domain`](apps/custom-domain) | Centralized custom domain management with DNS verification and SSL provisioning. | [docs](docs/apps/custom-domain/index.md) | <code>custom-domain-v<!-- v:custom-domain -->0.0.0<!-- /v --></code> |
| [`frontend`](apps/frontend) | Frontend application server (FastAPI) serving the website single page application. | [docs](docs/apps/frontend/index.md) | <code>frontend-v<!-- v:frontend -->0.0.0<!-- /v --></code> |
| [`internal`](apps/internal) | Internal admin dashboard for managing platform services. | [docs](docs/apps/internal/index.md) | <code>internal-v<!-- v:internal -->0.0.0<!-- /v --></code> |
| [`knowledge`](apps/knowledge) | Vector storage and semantic search SaaS for AI agents, LLMs and RAG applications. | [docs](docs/apps/knowledge/index.md) | <code>knowledge-v<!-- v:knowledge -->0.0.0<!-- /v --></code> |
| [`mailler`](apps/mailler) | Internal email sending service with multi-provider support, campaigns and inbound processing. | [docs](docs/apps/mailler/index.md) | <code>mailler-v<!-- v:mailler -->0.0.0<!-- /v --></code> |
| [`mta-sts`](apps/mta-sts) | Minimal FastAPI service serving the MTA-STS policy (RFC 8461). | [docs](docs/apps/mta-sts/index.md) | <code>mta-sts-v<!-- v:mta-sts -->0.0.0<!-- /v --></code> |
| [`reachy-mini-api`](apps/reachy-mini-api) | Internal API for the Reachy Mini robot: reports, status and a WebSocket channel. | [docs](docs/apps/reachy-mini-api/index.md) | <code>reachy-mini-api-v<!-- v:reachy-mini-api -->0.0.0<!-- /v --></code> |
| [`team`](apps/team) | Multi-agent orchestration platform: AI agents, workflows, tasks and memory behind a REST API. | [docs](docs/apps/team/index.md) | <code>team-v<!-- v:team -->0.0.0<!-- /v --></code> |
| [`vpn-portal`](apps/vpn-portal) | Zero-Trust VPN authentication and certificate issuance service. | [docs](docs/apps/vpn-portal/index.md) | <code>vpn-portal-v<!-- v:vpn-portal -->0.0.0<!-- /v --></code> |
| [`webhooks`](apps/webhooks) | FastAPI gateway receiving provider webhooks and forwarding them to internal services. | [docs](docs/apps/webhooks/index.md) | <code>webhooks-v<!-- v:webhooks -->0.0.0<!-- /v --></code> |
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

Applications that render HTML can have behave scenarios tagged `@browser` that
run in a real browser through Playwright. Install the browser once with
`uv run playwright install chromium`, skip those scenarios with
`E2E_SKIP_BROWSER=1` or `-t ~@browser`; see
[docs/testing](docs/testing/index.md) for the library and
[CONTRIBUTING.md](CONTRIBUTING.md) for the `E2E_*` variables.

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
