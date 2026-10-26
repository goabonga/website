# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Console capture, error assertions and the artifacts kept for failed scenarios."""

import contextlib
import zipfile
from dataclasses import replace

import pytest
from e2e_support.diagnostics import Diagnostics, Entry, slugify


@pytest.fixture
def scenario_factory(browser_session, site, tmp_path, monkeypatch):
    """Open scenarios whose artifacts go to a temporary directory."""
    monkeypatch.setattr(
        browser_session, "settings", replace(browser_session.settings, artifacts_dir=tmp_path)
    )
    opened = []

    def open_scenario(name):
        scenario = browser_session.new_scenario(name, base_url=site.url)
        opened.append(scenario)
        return scenario

    yield open_scenario
    for scenario in opened:
        with contextlib.suppress(Exception):  # already finished by the test
            scenario.context.close()


@pytest.mark.browser
def test_console_messages_are_recorded(scenario_factory):
    scenario = scenario_factory("console")
    scenario.page.goto("/console")
    kinds = [(entry.kind, entry.level, entry.text) for entry in scenario.diagnostics.entries]
    assert ("console", "log", "fine") in kinds
    assert ("console", "error", "boom from console") in kinds


@pytest.mark.browser
def test_uncaught_page_errors_are_recorded(scenario_factory):
    scenario = scenario_factory("crash")
    scenario.page.goto("/crash")
    scenario.page.wait_for_timeout(100)
    assert [entry.text for entry in scenario.diagnostics.errors] == ["kaput"]
    assert scenario.diagnostics.errors[0].kind == "pageerror"


@pytest.mark.browser
def test_a_clean_page_passes_the_error_assertion(scenario_factory):
    scenario = scenario_factory("clean")
    scenario.page.goto("/hello")
    scenario.assert_no_browser_errors()


@pytest.mark.browser
def test_the_error_assertion_lists_what_the_browser_reported(scenario_factory):
    scenario = scenario_factory("assertion")
    scenario.page.goto("/console")
    with pytest.raises(AssertionError, match=r"(?s)1 error\(s\).*boom from console"):
        scenario.assert_no_browser_errors()


@pytest.mark.browser
def test_ignored_errors_are_tolerated(scenario_factory):
    scenario = scenario_factory("ignored")
    scenario.page.goto("/console")
    scenario.assert_no_browser_errors(ignore=[r"boom from \w+"])


@pytest.mark.browser
def test_a_passed_scenario_saves_nothing(scenario_factory, tmp_path):
    scenario = scenario_factory("passed")
    scenario.page.goto("/hello")
    assert scenario.finish(failed=False) == []
    assert list(tmp_path.iterdir()) == []


@pytest.mark.browser
def test_a_failed_scenario_saves_screenshot_trace_html_and_console_log(scenario_factory, tmp_path):
    scenario = scenario_factory("Login: wrong password!")
    scenario.page.goto("/console")
    saved = scenario.finish(failed=True)

    directory = tmp_path / "Login-wrong-password"
    assert sorted(path.name for path in saved) == [
        "console.log",
        "page.html",
        "screenshot.png",
        "trace.zip",
    ]
    assert all(path.parent == directory for path in saved)
    assert (directory / "screenshot.png").read_bytes().startswith(b"\x89PNG")
    html = (directory / "page.html").read_text(encoding="utf-8")
    assert "Hello /console" in html
    assert "/console" in html.splitlines()[0]
    assert "[console:error] boom from console" in (directory / "console.log").read_text()
    assert zipfile.is_zipfile(directory / "trace.zip")


@pytest.mark.browser
def test_every_open_page_is_captured(scenario_factory, tmp_path):
    scenario = scenario_factory("two pages")
    scenario.page.goto("/hello")
    second = scenario.context.new_page()
    second.goto(f"{scenario.base_url}/other")
    scenario.finish(failed=True)
    assert (tmp_path / "two-pages" / "page-2.html").exists()
    assert (tmp_path / "two-pages" / "screenshot-2.png").exists()


@pytest.mark.browser
def test_the_trace_is_skipped_when_disabled(browser_session, site, tmp_path, monkeypatch):
    settings = replace(browser_session.settings, artifacts_dir=tmp_path, trace=False)
    monkeypatch.setattr(browser_session, "settings", settings)
    scenario = browser_session.new_scenario("no trace", base_url=site.url)
    scenario.page.goto("/hello")
    saved = scenario.finish(failed=True)
    assert "trace.zip" not in [path.name for path in saved]


@pytest.mark.browser
def test_scenarios_with_the_same_name_get_distinct_directories(scenario_factory, tmp_path):
    first = scenario_factory("same")
    second = scenario_factory("same")
    first.finish(failed=True)
    second.finish(failed=True)
    assert (tmp_path / "same" / "console.log").exists()
    assert (tmp_path / "same-2" / "console.log").exists()


def test_slugify_makes_names_safe_for_the_file_system():
    assert slugify("Feature: log in / out?") == "Feature-log-in-out"
    assert slugify("Feature - Scenario") == "Feature-Scenario"
    assert slugify("???") == "scenario"
    assert len(slugify("x" * 500)) == 100


def test_entries_render_with_their_origin():
    entry = Entry("console", "error", "bad", "http://x/app.js:3")
    assert str(entry) == "[console:error] bad (http://x/app.js:3)"
    assert entry.is_error
    assert not Entry("console", "log", "ok").is_error


def test_ignore_patterns_are_regular_expressions():
    class Context:
        def on(self, *_args):
            pass

    diagnostics = Diagnostics(Context())
    diagnostics.entries.append(Entry("console", "error", "GET /favicon.ico 404"))
    diagnostics.assert_clean(ignore=[r"favicon\.ico"])
    with pytest.raises(AssertionError):
        diagnostics.assert_clean(ignore=[r"nothing"])
    diagnostics.clear()
    assert diagnostics.render() == ""
