# CI job summaries

Each tool job of the `ci` workflow ends with a step that turns the report of
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
| `lint` | `ruff.json` | `ruff-check` | findings by rule and location, also written as inline annotations on the pull request |
| `lint` | `ruff-format.txt` | `ruff-format` | the files that would be reformatted |
| `license-headers` | `headers.txt` | `headers` | the files without their SPDX header |
| `test (<app>)` | `junit.xml`, `coverage.xml` | `pytest --junit J --coverage C` | totals, failed tests, and the files below 100% coverage with their missing lines |
| `bandit` | `bandit.json` | `bandit` | the issues by severity |
| `pip-audit` | `pip-audit.txt` | `text pip-audit` | the end of the output of the tool |
| `osv-scanner` | `osv-scanner.txt` | `text osv-scanner` | the end of the output of the tool |

A tool without a structured report goes through the `text` command, which
shows the last 40 lines of its output and takes the result from the
`JOB_STATUS` variable (`job.status`). When the report file is missing, the
section says that the tool did not run to completion instead of failing.

The steps that pipe a tool into `tee` run with `shell: bash`, which enables
`pipefail`, so `tool | tee report.txt` keeps the status of the tool. The other
steps keep the default shell of the runner.

The `multicz`, `docs`, `ansible`, `scripts` and `libs` jobs have no summary:
`multicz`, `zensical` and `ansible` print a short output, and the `scripts` and
`libs` jobs do not write a report. The release job already writes the plan of
`multicz` to its summary.
