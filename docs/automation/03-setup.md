# Setup

## Secrets and variables

Repository secrets:

| Name | Used for |
| --- | --- |
| `AUTO_MERGE_PAT` | Personal access token of the maintainer. It pushes the signed branches and `main`, adds the `auto-merge` label and writes the comments, so that they appear under the maintainer account and start workflows. Needs access to this repository with `contents`, `pull requests` and `issues` write permissions. |
| `GPG_PRIVATE_KEY` | Armored private key of the maintainer. |
| `GPG_PASSPHRASE` | Passphrase of that key. Used by `dependabot-rewrite` and `resign`, and by the merge. |

Repository variables:

| Name | Used for |
| --- | --- |
| `GIT_USER_NAME` | Name of the author and committer of the signed commits. |
| `GIT_USER_EMAIL` | Email of the author and committer. It must be a verified email of the account that owns the public key. |
| `GIT_SIGNING_KEY` | Identifier of the key to sign with, which must be in `GPG_PRIVATE_KEY`. |

No repository name, owner or email is written in the workflows or in the
scripts: they come from these values and from the GitHub context.

`RELEASE_PAT` (see [Production deployment](../ansible/08-production-deployment.md))
is a separate secret for the release and deploy workflows. Nothing prevents
using the same token for both.

## Repository settings

- **Verified commits.** Upload the public key to the account that owns
  `AUTO_MERGE_PAT`. `dependabot-auto-merge` only labels pull requests whose
  commits GitHub shows as verified.
- **Ruleset on `main`.** Require status checks (the list is read by the queue,
  which never sees a check as ready for a ruleset without any), signed commits and a linear
  history. The owner of `AUTO_MERGE_PAT` must be allowed to push to `main`
  despite the rules, as a bypass actor, since the queue fast-forwards `main`
  directly. A rule of the classic branch protection is not read by the queue.
- **Label.** Create the `auto-merge` label.
- **Workflow permissions.** The workflows declare their own permissions; the
  default token permissions of the repository can stay read-only.
- **Deployment branches.** `deploy/production` and `deploy/production-*` keep
  their own protection and the review of the `production` environment.
- **Dependabot secrets.** Workflows started on behalf of Dependabot may read
  the Dependabot secrets instead of the Actions secrets. If a run of
  `dependabot-rewrite` or `dependabot-auto-merge` reports a missing secret,
  add the same secrets as Dependabot secrets.

## Not verified

These workflows were written by porting a pipeline that works in other
repositories and were checked offline: the unit tests of the scripts, the
syntax of the workflows with `actionlint`, and a dry run of the rewrite script
on a scratch repository. They have never run on GitHub, so these points are
unverified:

- the rights of `AUTO_MERGE_PAT`, and that a ruleset lets it fast-forward
  `main`;
- the Dependabot secrets behaviour described above;
- the shape of `multicz plan --output json` with the components of this
  repository in a real run, and the exclusion of the `deploy-*` components;
- the names of the required checks read from the ruleset, against the jobs of
  `ci`;
- GitHub's verification of the signed commits, and the rewrite scopes on a real
  Dependabot pull request.
