# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""The behave hooks give @browser scenarios a page and skip them when browsers cannot run."""

import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

FEATURES = Path(__file__).parent / "behave_project" / "features"
HOOK_FEATURES = ("hooks.feature", "tagged_feature.feature")


def run_behave(tmp_path, *args, features=HOOK_FEATURES, project=FEATURES, **env):
    """Run behave on the test project and return (process, scenario counts)."""
    environment = {
        **os.environ,
        "E2E_ARTIFACTS_DIR": str(tmp_path / "artifacts"),
        "E2E_SKIP_BROWSER": "",
        **env,
    }
    process = subprocess.run(
        [
            sys.executable,
            "-m",
            "behave",
            *(str(project / name) for name in features),
            "--no-color",
            "-f",
            "plain",
            *args,
        ],
        capture_output=True,
        text=True,
        env=environment,
        cwd=tmp_path,
        check=False,
    )
    summary = re.search(
        r"(\d+) scenarios? passed, (\d+) failed, (\d+) skipped", process.stdout, re.MULTILINE
    )
    assert summary, process.stdout + process.stderr
    counts = dict(zip(("passed", "failed", "skipped"), map(int, summary.groups()), strict=True))
    return process, counts


@pytest.mark.browser
def test_browser_scenarios_run_with_a_page(browser_session, tmp_path):
    process, counts = run_behave(tmp_path, "--tags=~@fails")
    assert process.returncode == 0, process.stdout + process.stderr
    assert counts == {"passed": 5, "failed": 0, "skipped": 1}  # one excluded by tag


@pytest.mark.browser
def test_a_failed_browser_scenario_keeps_its_artifacts(browser_session, tmp_path):
    process, counts = run_behave(tmp_path, "--tags=@fails")
    assert process.returncode != 0
    assert counts == {"passed": 0, "failed": 1, "skipped": 5}  # the others are excluded by tag
    directory = (
        tmp_path / "artifacts" / "Browser-hooks-A-failing-browser-scenario-keeps-its-artifacts"
    )
    assert (directory / "screenshot.png").exists()
    assert (directory / "trace.zip").exists()
    assert "boom from console" in (directory / "console.log").read_text()
    assert "artifacts saved in" in process.stdout


def test_browser_scenarios_are_skipped_when_disabled(tmp_path):
    process, counts = run_behave(tmp_path, "--tags=~@fails", E2E_SKIP_BROWSER="1")
    assert process.returncode == 0, process.stdout + process.stderr
    assert counts == {"passed": 1, "failed": 0, "skipped": 5}
    assert process.stderr.count("@browser scenarios are skipped") == 1
    assert "E2E_SKIP_BROWSER" in process.stderr
    assert not (tmp_path / "artifacts").exists()


def test_browser_scenarios_are_skipped_with_a_clear_message_when_no_browser_is_installed(
    tmp_path,
):
    """Point Playwright at an empty browser directory: nothing can be launched."""
    process, counts = run_behave(
        tmp_path, "--tags=~@fails", PLAYWRIGHT_BROWSERS_PATH=str(tmp_path / "no-browsers")
    )
    assert process.returncode == 0, process.stdout + process.stderr
    assert counts == {"passed": 1, "failed": 0, "skipped": 5}
    assert "python -m playwright install chromium" in process.stderr
    assert process.stderr.count("@browser scenarios are skipped") == 1


@pytest.mark.browser
def test_step_screenshots_are_kept_for_every_step_when_asked(browser_session, tmp_path):
    process, counts = run_behave(tmp_path, "--tags=~@fails", E2E_SCREENSHOTS="steps")
    assert process.returncode == 0, process.stdout + process.stderr
    assert counts["failed"] == 0
    shots = sorted((tmp_path / "artifacts").glob("*/steps/*.png"))
    assert shots, process.stdout
    assert all(path.name[:2].isdigit() for path in shots)
    assert list((tmp_path / "artifacts").glob("*/screenshot.png"))


@pytest.mark.browser
def test_no_step_screenshot_is_kept_by_default(browser_session, tmp_path):
    process, _ = run_behave(tmp_path, "--tags=~@fails")
    assert process.returncode == 0, process.stdout + process.stderr
    assert not list((tmp_path / "artifacts").glob("**/*.png"))
