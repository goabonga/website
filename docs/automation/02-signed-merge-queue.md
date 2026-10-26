# Signed merge queue

The `auto-merge-signed` workflow merges a pull request into `main` when the
`auto-merge` label is added by someone with write access. The script behind it
is `scripts/ci_automation.py`; its tests are in `scripts/tests/`.

## Authorization

The workflow runs on `pull_request_target` (`labeled`) for pull requests into
`main`, only for the `auto-merge` label, on a pull request that is not a draft
and whose head is not a `deploy/` branch. Before anything else, and again
before every push, the script checks that:

- the pull request is open, comes from a branch of this repository, is still at
  the commit that was labelled and still carries the label;
- its base is `main` and its head is neither `main` nor a `deploy/` branch;
- the person who added the label still has `write`, `maintain` or `admin`
  permission;
- the signing key and the merge token are available.

A failure of the validation, the queue, the checks, the replay, the push or the
merge comments on the pull request and removes the label. To retry, fix the
problem and add the label again.

## The queue

One job runs per labelled pull request, and `concurrency` serializes the jobs of
a same pull request. Pull requests wait for each other with a poll every 30
seconds, for up to five hours:

- **Order.** The pull requests labelled before this one (the time of the latest
  `labeled` event decides) go first. Removing and adding the label again moves
  a pull request to the back.
- **Pending release.** `main` must have nothing left to release. The job checks
  out the latest `main` with its tags and runs `multicz plan --output json`;
  the components it would bump are pending. The `deploy-*` components are
  ignored, like the `release` job of `ci` does: only the deploy workflows bump
  them, after an apply, so they are nearly always pending.

When the pull request is first, the job waits for the checks of the head that
was labelled.

## Checks

The checks required are read from the rulesets that apply to `main`. The wait
fails when a check or a commit status failed, and goes on until every required
check is reported and completed with at least one success, so a run where
everything was skipped cannot merge. The job `merge into main` itself is
ignored. The wait stops after 25 minutes with an error; add the label again to
resume.

## Signing and merging

1. The commits of the branch are replayed on the latest `main`
   (`git rebase --force-rebase`). A branch containing merge commits is
   refused.
2. `scripts/sign_commit.py` runs after each pick. It checks the subject against
   the Conventional Commit types of `multicz.toml`, 72 characters at most,
   lowercase, without a final period, and re-authors and signs the commit with
   the maintainer identity. Attribution trailers (`Co-Authored-By`,
   `Signed-off-by`, `Generated with`) are dropped from the message, and so are
   `BREAKING CHANGE` footers and the `!` marker: a breaking change cannot go
   through this queue.
3. The signed commits are pushed to the pull request branch with
   `--force-with-lease`, so `ci` runs again on them, and the job waits for
   these checks.
4. `main` is fast-forwarded to the signed head. If `main` moved since the
   rebase the job fails and the label must be added again. As `main` is an
   ancestor of the pull request head, GitHub shows the pull request as merged.
5. The job comments on the pull request and deletes the branch (never `main`
   nor a `deploy/` branch). A failure to delete does not fail the merge.

The signing home and the key are removed at the end of the job, whatever the
result. The push to `main` starts `ci` on `main`, whose `release` job creates
the next releases: this is the release the next pull request of the queue
waits for.

## Re-signing

The `resign-signal` workflow runs for every push to a pull request into `main`
except Dependabot's and `deploy/` branches. It has no secrets and only starts
`resign` (`workflow_run`), which asks the script whether the head of the pull
request is still the pushed commit and whether a commit is not verified. Only
then does it check that the pusher has write access, replay the same commits
on the same base, sign them in place, push with a lease and comment. The signed
push runs the workflow again with nothing left to do.
