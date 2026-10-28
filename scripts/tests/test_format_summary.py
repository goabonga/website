# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""The Markdown job summaries written from the reports of the ci tools."""

import importlib.util
import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

SCRIPT = Path(__file__).parent.parent / "format_summary.py"
spec = importlib.util.spec_from_file_location("format_summary", SCRIPT)
assert spec is not None and spec.loader is not None
fs = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fs)


@pytest.fixture
def report(tmp_path: Path) -> Callable[[str, Any], str]:
    def write(name: str, content: Any) -> str:
        path = tmp_path / name
        _ = path.write_text(content if isinstance(content, str) else json.dumps(content))
        return str(path)

    return write


@pytest.fixture
def summary_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    path = tmp_path / "summary.md"
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(path))
    return path


def test_table_escapes_cells() -> None:
    assert (
        fs.table(["a", "b"], [("x|y", "l1\nl2")]) == "| a | b |\n| --- | --- |\n| x\\|y | l1 l2 |"
    )


def test_fenced_keeps_the_tail() -> None:
    text = fs.fenced("\n".join(str(n) for n in range(100)), limit=3)
    assert text == "```text\n... 97 earlier lines omitted\n97\n98\n99\n```"
    assert fs.fenced("one") == "```text\none\n```"


def test_relative_paths(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.chdir(tmp_path)
    assert fs.relative(str(tmp_path / "src" / "a.py")) == "src/a.py"
    assert fs.relative("/elsewhere/a.py") == "/elsewhere/a.py"


@pytest.mark.parametrize(
    "call",
    [
        fs.ruff_check,
        fs.ruff_format,
        fs.license_headers,
        fs.bandit_summary,
    ],
)
def test_a_missing_report_is_explained(call: Callable[[str | None], str]) -> None:
    assert "No report was produced" in call("/nonexistent/report")
    assert "No report was produced" in call(None)


def finding(code: str | None = "F401", filename: str = "src/a.py", row: int = 3) -> dict[str, Any]:
    return {
        "code": code,
        "filename": filename,
        "location": {"row": row, "column": 1},
        "message": "unused | import",
    }


def test_ruff_check_without_findings(report: Callable[[str, Any], str]) -> None:
    assert "## ruff check: passed" in fs.ruff_check(report("r.json", []))


def test_ruff_check_lists_findings_in_order(report: Callable[[str, Any], str]) -> None:
    text = fs.ruff_check(report("r.json", [finding(row=9), finding("E1", "src/a.py", 2)]))
    assert text.startswith("## ruff check: failed\n\n2 finding(s).")
    assert text.index("a.py:2") < text.index("a.py:9")
    assert "unused \\| import" in text


def test_ruff_annotations(report: Callable[[str, Any], str]) -> None:
    path = report("r.json", [finding(), finding(code=None)])
    lines = fs.ruff_annotations(path).splitlines()
    assert lines[0] == "::error file=src/a.py,line=3,col=1,title=F401::unused | import"
    assert "title=ruff::" in lines[1]
    assert fs.ruff_annotations("/nonexistent") == ""


def test_ruff_format_clean(report: Callable[[str, Any], str]) -> None:
    assert "29 files already formatted" in fs.ruff_format(
        report("f.txt", "29 files already formatted\n")
    )
    assert "Nothing to format" in fs.ruff_format(report("e.txt", ""))


def test_ruff_format_lists_files(report: Callable[[str, Any], str]) -> None:
    text = fs.ruff_format(
        report(
            "f.txt",
            "Would reformat: src/a.py\nWould reformat: src/b.py\n2 files would be reformatted\n",
        )
    )
    assert "2 file(s) would be reformatted" in text
    assert "- `src/a.py`" in text


def test_license_headers_clean(report: Callable[[str, Any], str]) -> None:
    text = fs.license_headers(report("h.txt", "All files have license headers.\n" * 5))
    assert "5 location(s) checked" in text


def test_license_headers_ignores_the_notices_of_uv(report: Callable[[str, Any], str]) -> None:
    output = (
        "Downloading cpython-3.11.18-linux-x86_64-gnu (download) (29.2MiB)\n"
        " Downloaded cpython-3.11.18-linux-x86_64-gnu (download)\n"
        "All files have license headers.\n"
    )
    text = fs.license_headers(report("h.txt", output))
    assert text.startswith("## SPDX license headers: passed")
    assert "1 location(s) checked" in text


def test_license_headers_missing(report: Callable[[str, Any], str]) -> None:
    output = (
        "Downloading cpython (download)\nMissing license headers in:\n - src/a.py\n - src/b.py\n"
    )
    text = fs.license_headers(report("h.txt", output))
    assert text.startswith("## SPDX license headers: failed")
    assert "2 file(s) without their header:" in text
    assert "- `src/a.py`\n- `src/b.py`" in text
    assert "Downloading" not in text


JUNIT = """<testsuites><testsuite name="pytest" tests="4" failures="1" errors="1" skipped="1" time="1.5">
<testcase classname="t.a" name="ok"/>
<testcase classname="t.a" name="bad"><failure message="boom">trace</failure></testcase>
<testcase classname="t.a" name="err"><error message="oops">trace</error></testcase>
<testcase classname="t.a" name="skip"><skipped/></testcase></testsuite></testsuites>"""

COVERAGE = """<coverage line-rate="0.75"><packages><package><classes>
<class filename="src/full.py"><lines><line number="1" hits="1"/></lines></class>
<class filename="src/gap.py"><lines><line number="1" hits="1"/><line number="2" hits="0"/><line number="3" hits="0"/><line number="4" hits="1"/></lines></class>
<class filename="src/empty.py"><lines/></class>
</classes></package></packages></coverage>"""


def test_pytest_summary_with_failures_and_gaps(
    report: Callable[[str, Any], str],
) -> None:
    text = fs.pytest_summary(report("j.xml", JUNIT), report("c.xml", COVERAGE))
    assert text.startswith("## pytest: failed")
    assert "| 4 | 1 | 2 | 1 | 1.50s |" in text
    assert "| t.a::bad | boom |" in text
    assert "| t.a::err | oops |" in text
    assert "Coverage: 75.0%" in text
    assert "| src/gap.py | 50.0% | 2, 3 |" in text
    assert "full.py" not in text


def test_pytest_summary_passing_and_fully_covered(
    report: Callable[[str, Any], str],
) -> None:
    junit = '<testsuite tests="2" failures="0" errors="0" skipped="0" time="0.1"><testcase classname="a" name="b"/></testsuite>'
    coverage = '<coverage line-rate="1"><packages><package><classes><class filename="a.py"><lines><line number="1" hits="1"/></lines></class></classes></package></packages></coverage>'
    text = fs.pytest_summary(report("j.xml", junit), report("c.xml", coverage))
    assert text.startswith("## pytest: passed")
    assert "Every file is fully covered." in text


def test_pytest_summary_without_coverage_or_junit(
    report: Callable[[str, Any], str],
) -> None:
    junit = '<testsuite tests="1" failures="0" errors="0" skipped="0" time="0"/>'
    assert "Coverage" not in fs.pytest_summary(report("j.xml", junit), None)
    assert "No report was produced" in fs.pytest_summary("/nonexistent", None)


def test_bandit_clean_and_dirty(report: Callable[[str, Any], str]) -> None:
    assert "628 lines scanned" in fs.bandit_summary(
        report("b.json", {"results": [], "metrics": {"_totals": {"loc": 628}}})
    )
    assert "No security issue found.\n" in fs.bandit_summary(report("b.json", {"results": []}))
    result = {
        "issue_severity": "HIGH",
        "test_id": "B602",
        "filename": "src/a.py",
        "line_number": 4,
        "issue_text": "shell",
    }
    text = fs.bandit_summary(report("b.json", {"results": [result]}))
    assert "## bandit: failed" in text
    assert "| HIGH | B602 | src/a.py:4 | shell |" in text


@pytest.mark.parametrize(
    ("status", "result"),
    [("success", "passed"), ("failure", "failed"), ("cancelled", "no report")],
)
def test_text_summary(report: Callable[[str, Any], str], status: str, result: str) -> None:
    text = fs.text_summary("osv", report("o.txt", "output"), status)
    assert text.startswith(f"## osv: {result}")


def test_text_summary_without_output(report: Callable[[str, Any], str]) -> None:
    assert "printed nothing" in fs.text_summary("osv", report("o.txt", " "), "success")
    assert "printed nothing" in fs.text_summary("osv", "/nonexistent", "success")


def vulnerable(name: str, version: str, vuln_id: str, fixes: list[str]) -> dict[str, Any]:
    vuln = {"id": vuln_id, "fix_versions": fixes, "aliases": ["CVE-1"], "description": "d"}
    return {"name": name, "version": version, "vulns": [vuln, vuln]}


def test_pip_audit_summary_clean(report: Callable[[str, Any], str]) -> None:
    content = {
        "dependencies": [
            {"name": "a", "version": "1", "vulns": []},
            {"name": "b", "version": "2", "vulns": []},
        ]
    }
    out = fs.pip_audit_summary(report("p.json", content), ["PYSEC-1", "PYSEC-2"])
    assert out.startswith("## pip-audit: passed")
    assert "2 packages audited, 0 advisories." in out
    assert "left out (see `osv-scanner.toml`): PYSEC-1, PYSEC-2." in out


def test_pip_audit_summary_with_advisories(report: Callable[[str, Any], str]) -> None:
    content = {
        "dependencies": [
            vulnerable("requests", "2.19.0", "PYSEC-2018-28", ["2.20.0"]),
            vulnerable("old", "1.0", "GHSA-x", []),
            {"name": "local", "version": "0", "skip_reason": "not on PyPI"},
        ]
    }
    out = fs.pip_audit_summary(report("p.json", content), [])
    assert out.startswith("## pip-audit: failed")
    assert "2 packages audited, 2 advisories." in out
    assert "Not audited: local." in out
    assert "| requests | 2.19.0 | PYSEC-2018-28 | CVE-1 | 2.20.0 |" in out
    assert "| old | 1.0 | GHSA-x | CVE-1 | none |" in out
    assert out.count("PYSEC-2018-28") == 1


def test_pip_audit_summary_without_report() -> None:
    assert "## pip-audit: no report" in fs.pip_audit_summary(None, [])


def test_osv_summary_clean_and_vulnerable(report: Callable[[str, Any], str]) -> None:
    assert fs.osv_summary(report("o.json", {"results": []})).startswith("## osv-scanner: passed")
    package = {
        "package": {"name": "requests", "version": "2.19.0"},
        "vulnerabilities": [{"id": "PYSEC-1", "summary": "leaks a header"}],
        "groups": [{"ids": ["PYSEC-1", "GHSA-1"], "max_severity": "7.5"}, {"ids": ["X"]}],
    }
    out = fs.osv_summary(report("o.json", {"results": [{"packages": [package]}]}))
    assert out.startswith("## osv-scanner: failed")
    assert "2 vulnerable package version(s)." in out
    assert "| requests | 2.19.0 | PYSEC-1, GHSA-1 | 7.5 | leaks a header |" in out
    assert "| requests | 2.19.0 | X | unknown |  |" in out


def test_osv_summary_without_report() -> None:
    assert "## osv-scanner: no report" in fs.osv_summary(None)


def test_multicz_summary_clean(report: Callable[[str, Any], str]) -> None:
    out = fs.multicz_summary(
        report("m.json", {"findings": [], "summary": {"errors": 0, "warnings": 0, "info": 0}})
    )
    assert out.startswith("## multicz: passed")
    assert "0 errors, 0 warnings, 0 info" in out
    assert "- the depends_on edges form no cycle" in out


def test_multicz_summary_with_findings(report: Callable[[str, Any], str]) -> None:
    finding = {
        "level": "error",
        "check": "bump_files_exist",
        "component": "auth",
        "message": "missing",
    }
    out = fs.multicz_summary(
        report(
            "m.json", {"findings": [finding], "summary": {"errors": 1, "warnings": 0, "info": 0}}
        )
    )
    assert out.startswith("## multicz: failed")
    assert "| error | bump_files_exist | auth | missing |" in out
    warning = {"findings": [], "summary": {"errors": 0, "warnings": 2, "info": 0}}
    assert fs.multicz_summary(report("w.json", warning)).startswith("## multicz: failed")


def test_multicz_summary_without_report() -> None:
    assert "## multicz: no report" in fs.multicz_summary(None)


def test_changed_summary_lists_every_component(report: Callable[[str, Any], str]) -> None:
    names = ["auth", "ansible", "playbook-site", "deploy-production", "e2e-support", "docs"]
    content = {
        "changed": ["auth", "deploy-production"],
        "all": names,
        "reason": "multicz changed",
        "since": "origin/main",
    }
    out = fs.changed_summary(report("c.json", content))
    assert out.startswith("## detect: 2 of 6 selected")
    assert "multicz changed. Compared with `origin/main`." in out
    assert "| auth | application | yes |" in out
    assert "| ansible | collection | no |" in out
    assert "| playbook-site | playbook | no |" in out
    assert "| deploy-production | deployment | yes |" in out
    assert "| e2e-support | library | no |" in out
    assert "| docs | group of files | no |" in out


def test_changed_summary_nothing_selected(report: Callable[[str, Any], str]) -> None:
    out = fs.changed_summary(
        report("c.json", {"changed": [], "all": ["auth"], "reason": "A release commit"})
    )
    assert out.startswith("## detect: nothing selected")
    assert "Compared with" not in out


def test_changed_summary_without_report() -> None:
    assert "## detect: no report" in fs.changed_summary(None)


def test_emit_appends_to_the_step_summary(summary_file: Path) -> None:
    fs.emit("one")
    fs.emit("two")
    assert summary_file.read_text() == "one\ntwo\n"


def test_emit_prints_without_a_step_summary(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.delenv("GITHUB_STEP_SUMMARY", raising=False)
    fs.emit("one")
    assert capsys.readouterr().out == "one\n"


def test_main_dispatches_every_command(
    report: Callable[[str, Any], str],
    summary_file: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv("JOB_STATUS", "success")
    ruff = report("r.json", [finding()])
    fs.main(["ruff-check", ruff])
    assert "::error file=src/a.py" in capsys.readouterr().out
    fs.main(["ruff-check", report("clean.json", [])])
    assert capsys.readouterr().out == ""
    fs.main(["ruff-format", report("f.txt", "1 file already formatted")])
    fs.main(["headers", report("h.txt", "All files have license headers.")])
    fs.main(["bandit", report("b.json", {"results": []})])
    fs.main(["osv-scanner", report("o.json", {"results": []})])
    fs.main(["pip-audit", report("a.json", {"dependencies": []}), "--ignored", "PYSEC-1"])
    fs.main(["multicz", report("m.json", {"findings": [], "summary": {}})])
    fs.main(["changed", report("c.json", {"changed": ["auth"], "all": ["auth"], "reason": "r"})])
    junit = '<testsuite tests="1" failures="0" errors="0" skipped="0" time="0"/>'
    fs.main(["pytest", "--junit", report("j.xml", junit)])
    content = summary_file.read_text()
    for title in (
        "ruff check",
        "ruff format",
        "SPDX license headers",
        "bandit",
        "osv-scanner",
        "pip-audit",
        "multicz",
        "detect",
        "pytest",
    ):
        assert f"## {title}: " in content


def test_main_requires_a_command() -> None:
    with pytest.raises(SystemExit):
        fs.main([])
