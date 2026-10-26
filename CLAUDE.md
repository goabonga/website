# CLAUDE.md

Monorepo of the platform services: a uv workspace of Python applications
plus the Ansible collection that provisions and deploys them.

The global rules in `~/.claude/CLAUDE.md` apply (repo coherence, atomic
commits, Conventional Commits, no `Co-Authored-By`). This file only adds
what is specific to this repository.

## Language

All code, comments, task names and documentation are written in English.

## Layout

- `apps/<name>/` - one uv workspace member per application.
- `ansible/` - Ansible collection (Galaxy layout) for provisioning and
  deployment.
- `docs/` - Zensical documentation site.

## Commit scopes

Valid scopes (kebab-case, singular). Never invent another one.

- Applications: `analytics`, `apt-server`, `asterisk`, `auth`, `backend`,
  `billing`, `custom-domain`, `frontend`, `internal`, `knowledge`,
  `mailler`, `mta-sts`, `reachy-mini-api`, `team`, `vpn-portal`,
  `webhooks`.
- `ansible` - the Ansible collection.
- `workspace` - root uv workspace, tooling, pre-commit, lint config.
- `multicz` - release configuration.
- `site` - documentation site configuration (nav, theme).

## Distribution

Applications are deployed from this repository by Ansible. Nothing is
published to PyPI and no Debian package is built.
