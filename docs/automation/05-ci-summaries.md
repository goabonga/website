# CI job summaries

Each job of the `ci` workflow ends with a step that turns the report of
the tool into a Markdown summary on the page of the run, so a failure can be
read without opening the log. The step only formats: the step of the tool has
already decided whether the job fails, and the summary runs even when it did
(`if: ${{ !cancelled() }}`).

`scripts/format_summary.py` reads the report and appends the section to
`$GITHUB_STEP_SUMMARY`, or prints it when the variable is not set, so it can be
tried locally:

```sh
uv run ruff check --output-format=json --output-file=ruff.json .
python3 scripts/format_summary.py ruff-check ruff.json
```

| Job | Report | Command | Section |
| --- | --- | --- | --- |
| `checks` (lint) | `ruff.json` | `ruff-check` | findings by rule and location, also written as inline annotations on the pull request |
| `checks` (format) | `ruff-format.txt` | `ruff-format` | the files that would be reformatted |
| `checks` (license) | `headers.txt` | `headers` | the files without their SPDX header |
| `checks` (bandit) | `bandit.json` | `bandit` | the issues by severity |
| `checks` (audit) | `pip-audit.json` | `pip-audit R --ignored ID...` | the packages audited, the advisories with their aliases and the version that fixes them, and the advisories accepted without a fix |
| `checks` (osv) | `osv-scanner.json` | `osv-scanner` | the vulnerable package versions with their advisories, severity and summary |
| `unit` | `junit.xml`, `coverage.xml` | `pytest --junit J --coverage C` | totals, failed tests, and the files below 100% coverage with their missing lines (no coverage for `scripts`) |
| `behave` | `behave.txt` | `text behave` | the end of the output of the scenarios |
| `ansible` | `ansible.txt` | `text ansible-<check>` | the collection install and the output of the check |
| `docs-build`, `docs-deploy` | `docs.txt` | `text docs-build` | the end of the output of the site build |
| `commit-messages` | `commit-messages.txt` | `text commit-messages` | the end of the output of the check |
| `multicz` | `multicz.json` | `multicz` | the verdict of `multicz validate --strict`, the findings by level, check and component, and what was checked |
| `detect` | `changed.json` | `changed` | every component and group with whether it was selected, and the rule that selected them |
| `ci-pass` | `results.txt` | `text ci-pass` | the result of every job of the run, then the count of each result |
| `release-bump` | `bumped.txt` | `text release-bump` | the components bumped and their new versions |
| `release-<component>` | `release.txt` | `text release-<component>` | the release that was created |

A leg of a matrix writes its own summary: the title of each section carries the tool, the name of the job carries the component.

A tool without a structured report goes through the `text` command, which
shows the last 40 lines of its output and takes the result from the
`JOB_STATUS` variable (`job.status`). When the report file is missing, the
section says that the tool did not run to completion instead of failing.

The steps that pipe a tool into `tee` run with `shell: bash`, which enables
`pipefail`, so `tool | tee report.txt` keeps the status of the tool. The other
steps keep the default shell of the runner.


## Coverage and test results on Codecov

The `<app>-test` jobs upload the coverage (`coverage.xml`) and the test results
(`junit.xml`) of an application with `codecov/codecov-action`, under a flag named
after the application. The results use `report_type: test_results`, which is
what replaces the deprecated `codecov/test-results-action`. Because only the
changed applications are tested, `codecov.yml` declares one flag per application
with the path of its sources and enables `carryforward`: an application that was
not tested keeps the coverage of its last upload. The upload does not fail the
job when Codecov is unreachable or `CODECOV_TOKEN` is missing.

