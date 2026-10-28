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
3. Splits a group that only touches `uv.lock`, before the key is imported
   (see below).
4. Replays the commits of the branch on the merge base with
   `git rebase --exec`, running `scripts/rewrite_dependabot_commit.py` from
   `trusted/` after each pick. The script reads the `pyproject.toml` files of
   the branch as data. A split group is committed instead, one commit per
   dependency.
5. Force-pushes the branch with `--force-with-lease`, using `AUTO_MERGE_PAT`
   (or the workflow token when it is not set, see below).
6. Retitles the pull request after its commits: a single commit gives its
   subject, a group keeps its title under the type and scope of its first
   commit (`python3 scripts/rewrite_dependabot_commit.py title BASE..HEAD`).
7. Tracks the pull request with an issue (see below).

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

## Grouped updates

A group such as `dev-tools` bumps several dependencies in one commit that only
touches `uv.lock`, which would give all of them one type and one scope.
`scripts/split_dependabot_lock.py prepare` regenerates the lock one dependency
at a time with `uv lock --upgrade-package`, and `commit` replays the stored
states on the merge base, one commit per dependency, typed and scoped like a
single bump of the table above. The dependencies are those declared by the root
`pyproject.toml`, an application or a library. Runtime dependencies come first,
so the title of the pull request, which follows the first commit, carries the
type that triggers a release.

The group stays a single commit, rewritten as `chore(workspace)`, when the head
changes more than `uv.lock`, when fewer than two declared dependencies moved,
when a package is locked in several versions, when `uv` fails, or when the
lock regenerated one dependency at a time differs from the one Dependabot
proposed (a transitive dependency moved too).

`uv lock` runs in the checkout of the pull request before the signing key is
imported, but after the checkout that holds `AUTO_MERGE_PAT` in its git
configuration: it resolves the lock, and Dependabot only changes versions.

## Issue tracking

`scripts/dependabot_issue.py link` creates an issue titled like the pull
request, labelled `dependencies` and assigned to the repository owner, and adds
`Closes #N` to the description of the pull request. Merging through the
interface then closes the issue by itself. When the title changes, the issue is
renamed. The issue is found again through a hidden marker in its body, never
through the description of the pull request, which Dependabot rewrites when it
recreates the pull request: the next run puts the keyword back.

When a Dependabot pull request is closed, the `close-issue` job runs
`scripts/dependabot_issue.py close` from the default branch. It closes the issue
as completed when the pull request was merged, which covers the signed merge,
and as not planned when Dependabot or a maintainer dropped it. Both use the
workflow token with `issues: write`.

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
