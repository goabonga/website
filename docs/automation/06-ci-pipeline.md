# The ci pipeline

The `ci` workflow runs on pull requests into `main` and on pushes to `main`. Its work is spread over three matrices, one
for the checks, one for the unit tests and one for the behave scenarios, whose legs are built from what multicz reports
as changed. The shape follows the pipeline of [`test-pipelilne-multicz`](https://github.com/goabonga/test-pipelilne-multicz).

## What runs for a change

`detect` runs `multicz changed` against the base of the pull request, or against the previous tip of `main` on a push,
and publishes the result as JSON (`{"changed": ["auth", "deploy-production"]}`). **multicz owns the dependencies**:
the list contains the components whose files changed and, through `depends_on`, the components downstream of them.

- A change to `auth` selects `auth` and `deploy-production`.
- A change to `ansible` selects the three playbooks and `deploy-production`.
- A change to `libs/e2e-support` selects `e2e-support` and the five applications that use it.

`detect` adds five names for what multicz does not track: `docs` (`docs/`, `zensical.toml`, `assets/`), `scripts`,
`workflows` (`.github/`), `workspace` (the toml files of the root) and `collection` (the Ansible collection or a
playbook changed). A change to something shared (`uv.lock`, the root `pyproject.toml`, `ci.yml` or the local actions)
selects everything. The `chore(release)` commit of multicz selects nothing: what it contains was tested before.

## The three matrices

`scripts/ci_matrix.py` turns the selection into the matrices, and `detect` publishes them as outputs:

| Job | One leg per | Runs |
| --- | --- | --- |
| `checks` | selected component and check | `license`, `lint`, `format`, `bandit`, `audit` (pip-audit) and `osv` (osv-scanner) for an application; the first four for `e2e-support`; `license`, `lint` and `format` for `scripts`; `license` for `workflows` and `workspace` |
| `unit` | selected application, `e2e-support` and `scripts` | `pytest`, with coverage sent to Codecov under the flag of the application |
| `behave` | selected application that has a `features` directory | the behave scenarios, the browser ones included |

`unit` waits for `checks` and `behave` waits for `unit`, so nothing runs tests on code that fails a check. A matrix with
nothing to run is skipped and does not stop the next one; a failed leg does (`!failure() && !cancelled()`). The legs do
not stop each other (`fail-fast: false`). `audit` and `osv` check the locked dependencies of the application alone
(`uv export --package`). The collection has its own matrix, `ansible` (`syntax` and `argspec`), and `docs-build` builds
the site; `commit-messages` (pull requests) and `multicz` (`multicz validate --strict`) always run.

All the steps of a check live in the local action `.github/actions/app-check`, so a matrix is a name, a gate and a handful
of inputs. The checks of a component run on the whole matrix before the tests start: a failed check of one application
holds back the tests of the others, which is the price of a matrix.

## The version under test

`unit`, `behave`, `ansible` and `docs-build` start with the local action `.github/actions/bump-preview`. It runs
`multicz bump --no-post-bump --no-changelog`: the version files of every component that would be bumped are written in
the workspace, and nothing is committed, tagged or pushed. What is tested or built carries the version the release will
publish, in the run of the pull request as well as in the run of the release. These jobs check out the whole history
(`fetch-depth: 0`), which multicz needs to compute the next versions.

Every job ends with a step that writes a summary of its result on the page of the run, with
`scripts/format_summary.py` (see [CI job summaries](05-ci-summaries.md)).

## The release

`ci-pass` needs every other job and fails when one of them failed or was cancelled; the jobs that were skipped because
nothing they cover changed do not count. It is the only check to require in the ruleset of `main`.

On `main`, once `ci-pass` is green, `release-bump` runs `multicz bump --commit --tag --push` for every component
except the `deploy-*` ones, which only the deploy workflows bump, and `e2e-support`, which is not released. It writes
one commit and one tag per component and exposes the new version of each as an output (`<component>_version`, with
underscores). Each `release-<component>` job (the sixteen applications, `ansible` and the three playbooks) runs only when
its output is not empty and creates the GitHub release of the tag with the notes of its changelog, through the local
action `.github/actions/publish-release`: modifying `auth` releases `auth` and nothing else. The release of `ansible`
carries the collection tarball. `docs-deploy` builds the site and publishes it to GitHub Pages when something was bumped.

The commit, the tags and the releases are pushed with `RELEASE_PAT` when it exists: a push or a release made with the
default token starts no workflow and cannot pass the ruleset of `main`.
