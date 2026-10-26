# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""The generic steps drive a real browser through a behave project."""

import pytest
from test_behave_hooks import run_behave


@pytest.mark.browser
def test_generic_steps_drive_the_toy_site(browser_session, tmp_path):
    process, counts = run_behave(tmp_path, "--tags=~@fails", features=("steps.feature",))
    assert process.returncode == 0, process.stdout + process.stderr
    assert counts == {"passed": 5, "failed": 0, "skipped": 1}
    assert (tmp_path / "artifacts" / "screenshots" / "Dashboard-home.png").exists()


@pytest.mark.browser
def test_a_missing_target_fails_with_a_clear_message(browser_session, tmp_path):
    process, counts = run_behave(
        tmp_path, "--tags=@fails", "--no-capture", features=("steps.feature",), E2E_TIMEOUT="500"
    )
    assert counts["failed"] == 1
    assert 'nothing on the page matches a button, link or text "Nonexistent button"' in (
        process.stdout
    )


def test_a_browser_step_without_the_tag_explains_what_is_missing(tmp_path):
    process, counts = run_behave(tmp_path, features=("no_browser_tag.feature",))
    assert counts["failed"] == 1
    assert "tag the scenario or the feature with @browser" in process.stdout
