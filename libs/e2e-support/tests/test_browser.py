# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""The browser session launches one browser and isolates scenarios in contexts."""

import threading
from dataclasses import replace

import pytest
from e2e_support import browser as browser_module
from e2e_support.browser import BrowserSession, BrowserUnavailable
from e2e_support.settings import E2ESettings
from playwright.sync_api import Error as PlaywrightError


@pytest.mark.browser
def test_a_scenario_navigates_relative_to_its_base_url(browser_session, site):
    scenario = browser_session.new_scenario("navigate", base_url=site.url)
    try:
        scenario.page.goto("/hello")
        assert scenario.page.title() == "Page /hello"
        assert scenario.page.url == f"{site.url}/hello"
    finally:
        scenario.close()


@pytest.mark.browser
def test_scenarios_do_not_share_cookies(browser_session, site):
    first = browser_session.new_scenario("first", base_url=site.url)
    second = browser_session.new_scenario("second", base_url=site.url)
    try:
        first.page.goto("/set-cookie")
        first.page.goto("/again")
        assert "visited=yes" in first.page.inner_text("#cookie")
        second.page.goto("/again")
        assert "visited" not in second.page.inner_text("#cookie")
    finally:
        first.close()
        second.close()


@pytest.mark.browser
def test_the_default_timeout_comes_from_the_settings(browser_session, site, monkeypatch):
    monkeypatch.setattr(
        browser_session, "settings", replace(browser_session.settings, timeout=1234)
    )
    scenario = browser_session.new_scenario("timeout", base_url=site.url)
    try:
        scenario.page.goto("/")
        with pytest.raises(PlaywrightError, match="1234ms"):
            scenario.page.click("#missing")
    finally:
        scenario.close()


@pytest.mark.browser
def test_context_options_are_passed_through(browser_session, site):
    scenario = browser_session.new_scenario("locale", base_url=site.url, locale="fr-FR")
    try:
        scenario.page.goto("/")
        assert scenario.page.evaluate("navigator.language") == "fr-FR"
    finally:
        scenario.close()


@pytest.mark.browser
def test_the_session_is_a_context_manager_and_stop_is_idempotent(browser_session):
    """Playwright's sync API allows one driver per thread, so use a fresh thread."""
    outcome = {}

    def run():
        try:
            with BrowserSession(browser_session.settings) as session:
                outcome["started"] = session.is_started
            outcome["stopped"] = not session.is_started
            session.stop()
        except BaseException as exc:
            outcome["error"] = exc

    thread = threading.Thread(target=run)
    thread.start()
    thread.join()
    assert "error" not in outcome, outcome.get("error")
    assert outcome == {"started": True, "stopped": True}


def test_using_a_session_that_is_not_started_is_refused():
    with pytest.raises(RuntimeError, match="not started"):
        BrowserSession(E2ESettings()).new_scenario("nope")


class _Playwright:
    """Stand-in for the Playwright driver whose browsers cannot be launched."""

    stopped = False

    def __init__(self, message):
        self.chromium = self
        self._message = message

    def launch(self, **_options):
        raise PlaywrightError(self._message)

    def stop(self):
        self.stopped = True


@pytest.mark.parametrize(
    ("message", "expected"),
    [
        (
            "BrowserType.launch: Executable doesn't exist at /x/chrome\nrun playwright install",
            "chromium browser is not installed (install it with: "
            "python -m playwright install chromium)",
        ),
        ("BrowserType.launch: missing libraries", "cannot launch chromium: BrowserType.launch"),
    ],
)
def test_a_browser_that_cannot_launch_is_reported_with_the_install_command(
    monkeypatch, message, expected
):
    driver = _Playwright(message)
    monkeypatch.setattr(
        browser_module, "sync_playwright", lambda: type("S", (), {"start": lambda _: driver})()
    )
    session = BrowserSession(E2ESettings())
    with pytest.raises(BrowserUnavailable) as raised:
        session.start()
    assert expected in str(raised.value)
    assert driver.stopped
    assert not session.is_started


@pytest.mark.browser
def test_a_passed_scenario_keeps_a_screenshot_when_screenshots_are_on(
    browser_session, site, monkeypatch, tmp_path
):
    monkeypatch.setattr(
        browser_session,
        "settings",
        replace(browser_session.settings, screenshots="scenario", artifacts_dir=tmp_path),
    )
    scenario = browser_session.new_scenario("shot", base_url=site.url)
    scenario.page.goto("/hello")
    saved = scenario.finish(failed=False)
    assert [path.name for path in saved] == ["screenshot.png"]
    assert saved[0].read_bytes().startswith(b"\x89PNG")


@pytest.mark.browser
def test_a_passed_scenario_keeps_nothing_by_default(browser_session, site):
    scenario = browser_session.new_scenario("no-shot", base_url=site.url)
    scenario.page.goto("/hello")
    assert scenario.finish(failed=False) == []


@pytest.mark.browser
def test_a_step_screenshot_is_numbered_and_named_after_the_step(browser_session, site):
    scenario = browser_session.new_scenario("steps", base_url=site.url)
    try:
        scenario.page.goto("/hello")
        first = scenario.capture_step("When I open /hello")
        scenario.page.goto("/other")
        second = scenario.capture_step("Then I see Page")
    finally:
        scenario.close()
    assert first.parent.name == "steps"
    assert [first.name, second.name] == ["01-When-I-open-hello.png", "02-Then-I-see-Page.png"]
    assert first.read_bytes().startswith(b"\x89PNG")


@pytest.mark.browser
def test_no_step_screenshot_is_kept_while_the_page_is_blank(browser_session, site):
    scenario = browser_session.new_scenario("blank", base_url=site.url)
    try:
        assert scenario.capture_step("Given nothing is open yet") is None
        scenario.page.goto("/hello")
        kept = scenario.capture_step("When I open /hello")
    finally:
        scenario.close()
    assert kept.name == "02-When-I-open-hello.png"  # the blank step still used number 1


@pytest.mark.browser
def test_a_step_that_changes_nothing_keeps_no_new_screenshot(browser_session, site):
    scenario = browser_session.new_scenario("unchanged-page", base_url=site.url)
    try:
        scenario.page.goto("/hello")
        assert scenario.capture_step("When I open /hello") is not None
        assert scenario.capture_step("Then I see Page") is None
    finally:
        scenario.close()


@pytest.mark.browser
def test_a_step_screenshot_of_a_closed_page_is_skipped(browser_session, site):
    scenario = browser_session.new_scenario("closed", base_url=site.url)
    scenario.page.close()
    assert scenario.capture_step("Then nothing") is None
    scenario.close()
