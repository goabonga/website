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
