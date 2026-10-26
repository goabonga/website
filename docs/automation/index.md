# Pull request automation

Pull requests into `main` are merged by GitHub Actions workflows that keep
the history linear and signed with the maintainer key. GitHub's own merge
buttons cannot do this: a squash or merge commit is signed by GitHub, and a
rebase merge replays the commits unsigned.

The pipeline for a Dependabot update, from the bump to `main`:

1. **Rewrite.** `dependabot-rewrite` re-authors the commits of the Dependabot
   branch as Conventional Commits with a scope of the closed list, signs them
   with the maintainer key and force-pushes the branch.
2. **Checks.** The push starts the `ci` workflow on the rewritten head.
3. **Label.** When `ci` succeeds and every commit is verified,
   `dependabot-auto-merge` adds the `auto-merge` label. A major update only
   gets a notice and waits for a maintainer to add the label.
4. **Queue.** The label starts `auto-merge-signed`. The pull request waits for
   the pull requests labelled before it and for the release pending on `main`.
5. **Sign and merge.** The commits are replayed on the latest `main`, signed,
   pushed, checked again and `main` is fast-forwarded to them.

A pull request written by a maintainer enters the pipeline at step 4: a
maintainer with write access adds the `auto-merge` label. If someone pushes
unsigned commits to a pull request branch, for example with GitHub's
"Update branch", `resign` signs them again in place.

The workflows never execute code from a pull request while the signing key or
the merge token is available: they run the scripts of the default branch
(`scripts/ci_automation.py`, `scripts/sign_commit.py` and
`scripts/rewrite-dependabot-commit.sh`) and treat the branch as data. The
branch's own code only runs in `ci`, before and after the signing.

Deployment pull requests are out of this pipeline. The branches
`deploy/production` and `deploy/production-<version>` are never labelled,
merged or re-signed: they need the approval of the protected `production`
environment (see [Production deployment](../ansible/08-production-deployment.md)).

## Pages

1. [Dependabot rewrite](01-dependabot-rewrite.md) - how the commits are
   re-authored, scoped and signed, and when a pull request is labelled.
2. [Signed merge queue](02-signed-merge-queue.md) - authorization, queue
   order, signing, merging and re-signing.
3. [Setup](03-setup.md) - the secrets, variables and repository settings the
   workflows need, and what has not been verified.
