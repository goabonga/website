#!/usr/bin/env python3

# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Turn the report of a CI tool into a GitHub job summary.

Each command reads the machine-readable report of one tool and appends a
Markdown section to ``$GITHUB_STEP_SUMMARY`` (to stdout when unset). It only
formats: the tool step has already decided whether the job fails.
"""

import argparse
import json
import os
import sys
import xml.etree.ElementTree as ET
from collections.abc import Iterable
from pathlib import Path
from typing import Any, NotRequired, TypedDict, cast


class RuffLocation(TypedDict):
    row: int
    column: int


class RuffFinding(TypedDict):
    code: str | None
    filename: str
    location: RuffLocation
    message: str


class BanditResult(TypedDict):
    issue_severity: str
    test_id: str
    filename: str
    line_number: int
    issue_text: str


class BanditTotals(TypedDict):
    loc: NotRequired[int]


class BanditMetrics(TypedDict):
    _totals: NotRequired[BanditTotals]


class BanditReport(TypedDict):
    results: list[BanditResult]
    metrics: NotRequired[BanditMetrics]


class JunitTotals(TypedDict):
    tests: int
    failures: int
    errors: int
    skipped: int
    time: float


class Arguments(argparse.Namespace):
    """The parsed command line, typed."""

    command: str = ""
    report: str = ""
    junit: str = ""
    coverage: str | None = None
    title: str = ""
    ignored: list[str] = []


PASSED, FAILED, NO_REPORT = "passed", "failed", "no report"
GROUPS = ("docs", "scripts", "workflows", "workspace", "collection")
MULTICZ_CHECKS = (
    "the bump files exist",
    "no two components claim the same paths",
    "the mirrors are owned by another component and form no cycle",
    "the depends_on edges form no cycle",
    "the changelogs are reachable",
    "the current version of every component can be resolved",
    "the writers validate against the repository",
    "the plugins report no problem",
)
TAIL_LINES = 40


def load_json(path: str | None) -> object | None:
    """The parsed report, which callers cast to the shape their tool writes."""
    if not (path and Path(path).is_file()):
        return None
    return cast(object, json.loads(Path(path).read_text()))


def read_text(path: str | None) -> str | None:
    return Path(path).read_text() if path and Path(path).is_file() else None


def relative(path: str | Path) -> str:
    """Paths in tool reports are absolute; show them from the workspace root."""
    try:
        return str(Path(path).relative_to(Path.cwd()))
    except ValueError:
        return str(path)


def cell(value: object) -> str:
    """A value that is safe inside a Markdown table cell."""
    return str(value).replace("|", "\\|").replace("\n", " ").strip()


def table(headers: list[str], rows: Iterable[Iterable[object]]) -> str:
    lines = ["| " + " | ".join(headers) + " |", "| " + " | ".join("---" for _ in headers) + " |"]
    lines += ["| " + " | ".join(cell(value) for value in row) + " |" for row in rows]
    return "\n".join(lines)


def fenced(text: str, limit: int = TAIL_LINES) -> str:
    lines = text.strip().splitlines()
    if len(lines) > limit:
        lines = [f"... {len(lines) - limit} earlier lines omitted", *lines[-limit:]]
    return "```text\n" + "\n".join(lines) + "\n```"


def missing_report(title: str, path: str | None) -> str:
    return f"## {title}: {NO_REPORT}\n\nNo report was produced (`{path}`): the tool did not run to completion.\n"


def ruff_check(path: str | None) -> str:
    findings = cast("list[RuffFinding] | None", load_json(path))
    if findings is None:
        return missing_report("ruff check", path)
    if not findings:
        return f"## ruff check: {PASSED}\n\nNo lint finding.\n"
    rows = [
        (f["code"], f"{relative(f['filename'])}:{f['location']['row']}", f["message"])
        for f in sorted(findings, key=lambda f: (f["filename"], f["location"]["row"]))
    ]
    return (
        f"## ruff check: {FAILED}\n\n{len(findings)} finding(s).\n\n"
        + table(["Rule", "Location", "Message"], rows)
        + "\n"
    )


def ruff_annotations(path: str | None) -> str:
    """Workflow annotations, so findings show inline on the pull request."""
    lines: list[str] = []
    findings = cast("list[RuffFinding]", load_json(path) or [])
    for f in findings:
        location = f["location"]
        title = f["code"] or "ruff"
        message = f["message"].replace("%", "%25").replace("\n", "%0A")
        lines.append(
            f"::error file={relative(f['filename'])},line={location['row']},col={location['column']},title={title}::{message}"
        )
    return "\n".join(lines)


def ruff_format(path: str | None) -> str:
    text = read_text(path)
    if text is None:
        return missing_report("ruff format", path)
    files = [
        line.split(": ", 1)[1] for line in text.splitlines() if line.startswith("Would reformat: ")
    ]
    if not files:
        return f"## ruff format: {PASSED}\n\n{text.strip().splitlines()[-1] if text.strip() else 'Nothing to format.'}\n"
    items = "\n".join(f"- `{name}`" for name in files)
    return f"## ruff format: {FAILED}\n\n{len(files)} file(s) would be reformatted; run `uv run ruff format`.\n\n{items}\n"


def license_headers(path: str | None) -> str:
    """The output of add_license_header.py --check: the files listed after "Missing license headers in:"."""
    text = read_text(path)
    if text is None:
        return missing_report("SPDX license headers", path)
    lines = text.splitlines()
    passed = sum(line.startswith("All files have license headers") for line in lines)
    # The other lines (the notices of uv about the interpreter it downloads) say nothing about the headers.
    missing = [line[3:].strip() for line in lines if line.startswith(" - ")]
    if not missing and not any(line.startswith("Missing license headers") for line in lines):
        return f"## SPDX license headers: {PASSED}\n\n{passed} location(s) checked, every file has its header.\n"
    return (
        f"## SPDX license headers: {FAILED}\n\n{len(missing)} file(s) without their header:\n\n"
        + "\n".join(f"- `{name}`" for name in missing)
        + "\n\nFix with `scripts/add_license_header.py` (without `--check`).\n"
    )


def junit_totals(path: str) -> tuple[JunitTotals, list[tuple[str, str]]]:
    root = ET.parse(path).getroot()
    suites = [root] if root.tag == "testsuite" else list(root.iter("testsuite"))
    totals = JunitTotals(
        tests=sum(int(s.get("tests", 0)) for s in suites),
        failures=sum(int(s.get("failures", 0)) for s in suites),
        errors=sum(int(s.get("errors", 0)) for s in suites),
        skipped=sum(int(s.get("skipped", 0)) for s in suites),
        time=sum(float(s.get("time", 0)) for s in suites),
    )
    failed: list[tuple[str, str]] = []
    for case in root.iter("testcase"):
        problem = case.find("failure") if case.find("failure") is not None else case.find("error")
        if problem is not None:
            failed.append(
                (f"{case.get('classname', '')}::{case.get('name', '')}", problem.get("message", ""))
            )
    return totals, failed


def coverage_files(path: str) -> tuple[float, list[tuple[str, float, str]]]:
    root = ET.parse(path).getroot()
    rows: list[tuple[str, float, str]] = []
    for item in root.iter("class"):
        lines = [line for line in item.iter("line")]
        missed = [line.attrib["number"] for line in lines if line.get("hits") == "0"]
        percent = 100 * (len(lines) - len(missed)) / len(lines) if lines else 100.0
        rows.append((item.get("filename", ""), percent, ", ".join(missed)))
    return float(root.get("line-rate", 0)) * 100, sorted(rows)


def pytest_summary(junit: str | None, coverage: str | None) -> str:
    if not (junit and Path(junit).is_file()):
        return missing_report("pytest", junit)
    totals, failed = junit_totals(junit)
    bad = totals["failures"] + totals["errors"]
    passed = totals["tests"] - bad - totals["skipped"]
    text = f"## pytest: {FAILED if bad else PASSED}\n\n"
    text += table(
        ["Tests", "Passed", "Failed", "Skipped", "Time"],
        [(totals["tests"], passed, bad, totals["skipped"], f"{totals['time']:.2f}s")],
    )
    if failed:
        text += "\n\n### Failed tests\n\n" + table(["Test", "Message"], failed)
    if coverage and Path(coverage).is_file():
        total, files = coverage_files(coverage)
        text += f"\n\n### Coverage: {total:.1f}%\n\n"
        gaps = [(name, f"{pct:.1f}%", missing) for name, pct, missing in files if pct < 100]
        text += (
            table(["File", "Cover", "Missing lines"], gaps)
            if gaps
            else "Every file is fully covered."
        )
    return text + "\n"


def bandit_summary(path: str | None) -> str:
    report = cast("BanditReport | None", load_json(path))
    if report is None:
        return missing_report("bandit", path)
    results = report["results"]
    if not results:
        totals = report.get("metrics", {}).get("_totals", {})
        loc = totals.get("loc")
        scanned = f" {loc} lines scanned." if loc else ""
        return f"## bandit: {PASSED}\n\nNo security issue found.{scanned}\n"
    rows = [
        (r["issue_severity"], r["test_id"], f"{r['filename']}:{r['line_number']}", r["issue_text"])
        for r in results
    ]
    return (
        f"## bandit: {FAILED}\n\n{len(results)} issue(s).\n\n"
        + table(["Severity", "Test", "Location", "Issue"], rows)
        + "\n"
    )


def text_summary(title: str, path: str | None, status: str) -> str:
    """A tool without a structured report: its status and the end of its output."""
    text = read_text(path)
    result = PASSED if status == "success" else FAILED if status == "failure" else NO_REPORT
    body = fenced(text) if text and text.strip() else "The tool printed nothing."
    return f"## {title}: {result}\n\n{body}\n"


def pip_audit_summary(path: str | None, ignored: list[str]) -> str:
    """The report of `pip-audit --format json`: what was audited, the advisories and the accepted ones."""
    report = cast("dict[str, Any] | None", load_json(path))
    if report is None:
        return missing_report("pip-audit", path)
    packages = cast("list[dict[str, Any]]", report.get("dependencies", []))
    found: dict[tuple[str, str, str], dict[str, Any]] = {}
    for package in packages:
        for vuln in cast("list[dict[str, Any]]", package.get("vulns", [])):
            found[(package["name"], package["version"], vuln["id"])] = vuln
    skipped = [p["name"] for p in packages if p.get("skip_reason")]
    result = FAILED if found else PASSED
    audited = len(packages) - len(skipped)
    lines = [f"## pip-audit: {result}", "", f"{audited} packages audited, {len(found)} advisories."]
    if ignored:
        lines.append(
            f"Accepted without a fix and left out (see `osv-scanner.toml`): {', '.join(ignored)}."
        )
    if skipped:
        lines.append(f"Not audited: {', '.join(sorted(skipped))}.")
    out = "\n".join(lines) + "\n"
    if found:
        rows = [
            (
                name,
                version,
                vuln["id"],
                ", ".join(vuln.get("aliases", [])),
                ", ".join(vuln.get("fix_versions", [])) or "none",
            )
            for (name, version, _), vuln in sorted(found.items())
        ]
        out += "\n" + table(["Package", "Version", "Advisory", "Aliases", "Fixed in"], rows) + "\n"
    return out


def osv_summary(path: str | None) -> str:
    """The report of `osv-scanner --format json`: the vulnerable packages and their advisories."""
    report = cast("dict[str, Any] | None", load_json(path))
    if report is None:
        return missing_report("osv-scanner", path)
    rows: list[tuple[str, str, str, str, str]] = []
    for result in cast("list[dict[str, Any]]", report.get("results", [])):
        for package in cast("list[dict[str, Any]]", result.get("packages", [])):
            info = cast("dict[str, str]", package.get("package", {}))
            summaries = {v["id"]: v.get("summary", "") for v in package.get("vulnerabilities", [])}
            for group in cast("list[dict[str, Any]]", package.get("groups", [])):
                ids = cast("list[str]", group.get("ids", []))
                rows.append(
                    (
                        info.get("name", ""),
                        info.get("version", ""),
                        ", ".join(ids),
                        str(group.get("max_severity", "")) or "unknown",
                        next((summaries[i] for i in ids if summaries.get(i)), ""),
                    )
                )
    if not rows:
        return f"## osv-scanner: {PASSED}\n\nNo known vulnerability in the locked dependencies.\n"
    rows.sort()
    return (
        f"## osv-scanner: {FAILED}\n\n{len(rows)} vulnerable package version(s).\n\n"
        + table(["Package", "Version", "Advisories", "Severity", "Summary"], rows)
        + "\n"
    )


def multicz_summary(path: str | None) -> str:
    """The report of `multicz validate --output json`: the verdict, the findings and what was checked."""
    report = cast("dict[str, Any] | None", load_json(path))
    if report is None:
        return missing_report("multicz", path)
    findings = cast("list[dict[str, Any]]", report.get("findings", []))
    totals = cast("dict[str, int]", report.get("summary", {}))
    counts = ", ".join(f"{totals.get(key, 0)} {key}" for key in ("errors", "warnings", "info"))
    result = FAILED if totals.get("errors", 0) or totals.get("warnings", 0) else PASSED
    out = f"## multicz: {result}\n\n`multicz validate --strict`: {counts}.\n\n"
    if findings:
        rows = [
            (f.get("level"), f.get("check"), f.get("component", ""), f.get("message"))
            for f in findings
        ]
        out += table(["Level", "Check", "Component", "Finding"], rows) + "\n\n"
    return out + "Checked:\n\n" + "\n".join(f"- {check}" for check in MULTICZ_CHECKS) + "\n"


def changed_summary(path: str | None) -> str:
    """The components `detect` selected, with the rule that selected them."""
    report = cast("dict[str, Any] | None", load_json(path))
    if report is None:
        return missing_report("detect", path)
    changed = set(cast("list[str]", report.get("changed", [])))
    names = cast("list[str]", report.get("all", []))
    selected = [name for name in names if name in changed]
    title = f"{len(selected)} of {len(names)} selected" if selected else "nothing selected"
    since = f" Compared with `{report['since']}`." if report.get("since") else ""
    rows = [(name, component_kind(name), "yes" if name in changed else "no") for name in names]
    return (
        f"## detect: {title}\n\n{report.get('reason', '')}.{since}\n\n"
        + table(["Component", "Kind", "Selected"], rows)
        + "\n"
    )


def component_kind(name: str) -> str:
    if name in GROUPS:
        return "group of files"
    if name == "ansible":
        return "collection"
    if name.startswith("playbook-"):
        return "playbook"
    if name.startswith("deploy-"):
        return "deployment"
    if name == "e2e-support":
        return "library"
    return "application"


def emit(text: str) -> None:
    target = os.environ.get("GITHUB_STEP_SUMMARY")
    if target:
        with Path(target).open("a") as stream:
            _ = stream.write(text + "\n")
    else:
        _ = sys.stdout.write(text + "\n")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    for name in (
        "ruff-check",
        "ruff-format",
        "headers",
        "bandit",
        "multicz",
        "changed",
        "osv-scanner",
    ):
        _ = sub.add_parser(name).add_argument("report")
    audit = sub.add_parser("pip-audit")
    _ = audit.add_argument("report")
    _ = audit.add_argument("--ignored", nargs="*", default=[])
    pytest = sub.add_parser("pytest")
    _ = pytest.add_argument("--junit", required=True)
    _ = pytest.add_argument("--coverage")
    text = sub.add_parser("text")
    _ = text.add_argument("title")
    _ = text.add_argument("report")
    args = parser.parse_args(argv, namespace=Arguments())
    if args.command == "ruff-check":
        annotations = ruff_annotations(args.report)
        if annotations:
            print(annotations)
        emit(ruff_check(args.report))
    elif args.command == "pytest":
        emit(pytest_summary(args.junit, args.coverage))
    elif args.command == "pip-audit":
        emit(pip_audit_summary(args.report, args.ignored))
    elif args.command == "text":
        emit(text_summary(args.title, args.report, os.environ.get("JOB_STATUS", "")))
    else:
        formatters = {
            "ruff-format": ruff_format,
            "headers": license_headers,
            "bandit": bandit_summary,
            "multicz": multicz_summary,
            "changed": changed_summary,
            "osv-scanner": osv_summary,
        }
        emit(formatters[args.command](args.report))


if __name__ == "__main__":
    main()
