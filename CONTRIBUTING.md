# Contributing to website

Thanks for taking the time to contribute. This document is the short version
of how to propose a change and what the project expects in return.

## Code of Conduct

Participation in this project is governed by the
[Code of Conduct](CODE_OF_CONDUCT.md). By contributing you agree to abide by
its terms.

## Repository layout

- `apps/<name>/` - one application per directory, each a member of the root
  [uv workspace](https://docs.astral.sh/uv/concepts/projects/workspaces/).
- `ansible/` - the Ansible collection that provisions hosts and deploys the
  applications.
- `docs/` - the Zensical documentation site, configured by `zensical.toml`.
- `scripts/` - repository tooling (SPDX header check).

## Development setup

```bash
git clone https://github.com/goabonga/website.git
cd website
uv sync
uv run pre-commit install --install-hooks -t pre-commit -t commit-msg
```

`uv sync` installs the root `dev` group (ruff, pytest, behave, ansible-core,
pre-commit) and every workspace member.

## Quality gates

Before pushing, make sure your change passes the same gates the `ci`
workflow runs.

Workspace-wide:

```bash
uv run ruff check .
uv run ruff format --check .
python scripts/add_license_header.py --path . --types toml --check
uvx multicz validate --strict
uv sync --only-group doc && uv run zensical build --clean   # documentation
```

Per application (replace `<app>` with the directory name under `apps/`):

```bash
uv run --package <app> --group dev pytest apps/<app>
uv run --package <app> --group dev behave apps/<app>/features
```

Both suites mock the database, Redis and SMTP, so they need no
infrastructure.

Changes under `ansible/` are checked with `ansible-playbook --syntax-check`
on the playbooks in `ansible/playbooks/`.

## Features

One feature is one logical unit of work, delivered in this order and as
separate commits:

1. `feat(<scope>)`: the implementation.
2. `test(<scope>)`: the pytest tests and the behave scenarios.
3. `docs(<scope>)`: the page under `docs/` (and the README or `pyproject.toml`
   if the feature justifies it).

Every commit builds and passes the tests on its own, and a file only
references things that exist at that commit.

## Commit messages

Commit messages MUST follow
[Conventional Commits](https://www.conventionalcommits.org/). They drive the
version bump and CHANGELOG computed by
[multicz](https://github.com/goabonga/multicz).

Format: `<type>(<scope>): <description>`, in the imperative mood, lowercase,
without a trailing period, 72 characters at most.

| Type | Effect on version | Use it for |
| --- | --- | --- |
| `feat` | minor | new capability |
| `fix` | patch | bug fix |
| `perf` | patch | performance improvement |
| `refactor`, `docs`, `test`, `chore`, `ci`, `build`, `style` | none | maintenance |
| `feat!` / `BREAKING CHANGE:` | major | incompatible change |

### Scopes

The scope is the module touched, in kebab-case. Use only these:

- Applications: `analytics`, `apt-server`, `asterisk`, `auth`, `backend`,
  `billing`, `custom-domain`, `frontend`, `internal`, `knowledge`,
  `mailler`, `mta-sts`, `reachy-mini-api`, `team`, `vpn-portal`, `webhooks`.
- `ansible` - the Ansible collection.
- `workspace` - root uv workspace, tooling, pre-commit, lint config.
- `multicz` - release configuration.
- `site` - documentation site configuration (nav, theme).

A commit touching two scopes must be split. Cross-cutting files (README,
`pyproject.toml`, docs navigation) are updated in the commit of the feature
that justifies them.

### Rules

- One commit is one logical change, and it can be reverted on its own.
- No opportunistic changes (reformatting, renaming, typo fixes) inside a
  feature commit.
- Do not append `Co-Authored-By` trailers or tool-attribution footers.
- History is rebased, not patched: fix your branch by amending or rewriting
  the commit that introduced the problem and force-push the branch, instead
  of adding `fix` commits on top of your own unmerged work.

## Releasing

Releases are automated: on every push to `main`, the `ci` workflow runs
`multicz bump` (signed commit and tag) and creates a GitHub Release for each
bumped component. Each component has its own version, changelog and tag
(`<component>-v<version>`). Maintainers do not bump versions or edit
changelogs by hand. Nothing is published to PyPI or Ansible Galaxy.

## Reporting bugs and asking for features

Please open a GitHub issue. For security-sensitive reports, follow
[SECURITY.md](SECURITY.md) instead of the public tracker.
