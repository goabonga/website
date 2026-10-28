# Dependabot rewrite

Dependabot commits are authored by the bot and signed by GitHub, with a
message that does not follow the scopes of this repository. The
`dependabot-rewrite` workflow fixes both before any check runs.

## When it runs

On `pull_request_target` events (`opened`, `synchronize`, `reopened`) for pull
requests into `main`. The workflow loaded is the one of the default branch.
The job runs only when the pull request was opened by `dependabot[bot]` from a
branch of this repository, and is skipped when:

- the head commit is no longer authored by Dependabot: it was already
  rewritten. The push of the rewritten branch starts the workflow again, and
  this check is what ends the loop;
- `GPG_PRIVATE_KEY` or `GPG_PASSPHRASE` is not set: the pull request keeps the
  bot-authored commits and a warning is written to the run summary.

## What it does

1. Checks out the default branch into `trusted/` and the pull request branch
   into `pr/`. The signing key is never imported next to code taken from the
   branch.
2. Imports the key, and takes the git name, email and signing key from it.
3. Replays the commits of the branch on the merge base with
   `git rebase --exec`, running `scripts/rewrite_dependabot_commit.py` from
   `trusted/` after each pick. The script reads the `pyproject.toml` files of
   the branch as data.
4. Force-pushes the branch with `--force-with-lease`, using `AUTO_MERGE_PAT`
   (or the workflow token when it is not set, see below).

Each commit is re-authored with `--reset-author`, signed, and its
`Co-authored-by` trailers are dropped.

## Type and scope

The scope must come from the closed list of `CLAUDE.md`, so the usual `deps`
scope is not used.

| Bump | Message prefix |
| --- | --- |
| GitHub Actions (the commit touches `.github/workflows/`) | `ci` |
| The `dev-tools` group of `dependabot.yml` | `chore(workspace)` |
| A package declared by one application only | `fix(<app>)` if it is a runtime dependency, `chore(<app>)` if it is in a dev group |
| A package declared by several applications | `fix` or `chore`, without a scope: a commit touching two scopes is not valid and no scope covers them all |
| Root tooling, or a transitive dependency (only `uv.lock` changes) | `chore(workspace)` |

A runtime dependency is one listed in `[project].dependencies` or
`[project.optional-dependencies]` of `apps/<app>/pyproject.toml`: it ships
with the application, so the bump must release it (`fix`). Dev groups do not
ship (`chore`).

The grouped update is kept as one commit. Splitting a grouped `uv.lock` update
into one commit per dependency is not done: the workspace declares its
dependencies in the `pyproject.toml` of each application, and the only group
(`dev-tools`) is meant to be a single `chore(workspace)` change.

## Why the push uses the merge token

A push made with the workflow token starts no workflow. Without
`AUTO_MERGE_PAT`, the rewritten head would never be checked by `ci`, and the
pull request would never be labelled. With the fallback to the workflow token
the rewrite still works, but the pull request has to be merged by hand.

## Labelling

`dependabot-auto-merge` runs when the `ci` workflow completes. It labels a pull
request with `auto-merge` only when all of these hold:

- the `ci` run succeeded, for a `pull_request` event on a `dependabot/` branch
  of this repository;
- the commit that was checked is still the head of exactly one open Dependabot
  pull request into `main`;
- every commit of the pull request is verified by GitHub, which means the
  rewrite happened and the public key is registered (see [Setup](03-setup.md));
- the update is not a major one. Major updates are read from the pull request
  description written by Dependabot. They get one comment (a hidden marker
  prevents repeating it), the owner of the token is assigned, and a maintainer
  reviews and adds the label.

The label is added with `AUTO_MERGE_PAT`: a label added with the workflow token
would not start `auto-merge-signed`, because GitHub does not chain workflow
events made by that token.
