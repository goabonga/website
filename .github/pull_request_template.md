## Description

<!-- Describe what this PR does and why. -->

## Type

<!-- Check the one that applies: -->

- [ ] `feat` - New feature
- [ ] `fix` - Bug fix
- [ ] `docs` - Documentation
- [ ] `refactor` - Code refactoring
- [ ] `test` - Adding or updating tests
- [ ] `chore` - Maintenance
- [ ] `ci` - CI / release pipeline

## Scope

<!-- An application, `ansible`, `workspace`, `multicz` or `site`. -->

## Changes

<!-- List the main changes introduced by this PR: -->

-

## Related Issues

<!-- Link related issues: Closes #123, Fixes #456 -->

## Checklist

- [ ] Commits follow [Conventional Commits](https://www.conventionalcommits.org/) with a valid scope (see CONTRIBUTING.md)
- [ ] Each commit is one logical change; no fix-up commits on top of this branch
- [ ] Branch is up to date with `main`
- [ ] `uv run ruff check .` and `uv run ruff format --check .` are clean
- [ ] `uv run --package <app> --group dev pytest apps/<app>` and `behave apps/<app>/features` pass (if an application changed)
- [ ] `ansible-playbook --syntax-check` passes (if the collection changed)
- [ ] `uvx multicz validate --strict` passes
- [ ] SPDX license headers are present (`python scripts/add_license_header.py --path . --types toml --check`)
- [ ] Documentation under `docs/` is updated
- [ ] No `Co-Authored-By` trailer in commit messages
