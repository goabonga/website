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
- `libs/<name>/` - support libraries that are not applications (for now
  `e2e-support`, the browser test tooling), also workspace members.
- `ansible/` - the Ansible collection that provisions hosts and deploys the
  applications.
- `docs/` - the Zensical documentation site, configured by `zensical.toml`.
- `scripts/` - repository tooling: the SPDX header check and the scripts of
  the pull request automation (with their tests in `scripts/tests/`).

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
uv run pytest scripts/tests
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

In CI, the `test` and `libs` jobs only run for what a pull request changes:
`multicz changed` lists the changed components, and the tests, scenarios
and sources of an application all belong to its component. A change to
`uv.lock`, the root `pyproject.toml`, `libs/` or `ci.yml` runs every
application.

Changes under `ansible/` are checked with `ansible-playbook --syntax-check`
on the playbooks in `ansible/playbooks/`.

### Browser scenarios

Applications that render HTML can have behave scenarios tagged `@browser`,
driven in a real browser with [Playwright](https://playwright.dev/python/)
through the `e2e-support` library (`libs/e2e-support`, documented in
`docs/testing/`). They run in the same `behave` command as the in-process
scenarios, which they complement.

The browser is a separate download, once per machine (add `--with-deps` to
install the system libraries too, which needs root):

```bash
uv run playwright install chromium
```

Run only the in-process scenarios, or only the browser ones:

```bash
uv run --package <app> --group dev behave apps/<app>/features -t ~@browser
uv run --package <app> --group dev behave apps/<app>/features -t @browser
```

`E2E_SKIP_BROWSER=1` skips the `@browser` scenarios without installing
anything, and they are skipped with an explanation (not failed) when the
browser is missing. The behavior is configured by environment variables:

| Variable | Default | Description |
| --- | --- | --- |
| `E2E_BROWSER` | `chromium` | `chromium`, `firefox` or `webkit` |
| `E2E_HEADLESS` | `true` | Set `0` to watch the browser |
| `E2E_SLOWMO` | `0` | Milliseconds between actions |
| `E2E_ARTIFACTS_DIR` | `artifacts` | Where failed scenarios save a screenshot, a trace, the HTML and the console log (git-ignored) |
| `E2E_SKIP_BROWSER` | `false` | Skip the `@browser` scenarios |
| `E2E_TIMEOUT` | `10000` | Action and expectation timeout, in milliseconds |
| `E2E_TRACE` | `true` | Record a trace, kept on failure (`python -m playwright show-trace <file>`) |

The library has its own tests, which launch a real browser:

```bash
uv run --package e2e-support --group dev pytest libs/e2e-support
```

In CI the browser is installed (and cached) only for the applications that
have `@browser` scenarios, and the artifacts of failed scenarios are uploaded
to the workflow run.

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

## Merging

Pull requests into `main` are not merged with GitHub's buttons. A maintainer
with write access adds the `auto-merge` label once the pull request is ready:
it then waits its turn in a queue, its commits are replayed on `main` and
signed with the maintainer key, and `main` is fast-forwarded to them. Commits
pushed unsigned to a pull request branch are signed again in place. Dependabot
pull requests are rewritten as Conventional Commits, and labelled
automatically unless they contain a major update. Deployment pull requests
(`deploy/production...`) are not part of this: they are approved through the
`production` environment. The signing removes `BREAKING CHANGE` footers and
the `!` marker from the messages, so a breaking change is not merged this
way. See the
[pull request automation](docs/automation/index.md) documentation.

## Releasing

Releases are automated: on every push to `main`, the `ci` workflow runs
`multicz bump` (signed commit and tag) and creates a GitHub Release for each
bumped component. Each component has its own version, changelog and tag
(`<component>-v<version>`). Maintainers do not bump versions or edit
changelogs by hand. Nothing is published to PyPI or Ansible Galaxy.

## Reporting bugs and asking for features

Please open a GitHub issue. For security-sensitive reports, follow
[SECURITY.md](SECURITY.md) instead of the public tracker.
