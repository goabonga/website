# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Playwright session management: one browser per run, one context per scenario."""

from __future__ import annotations

from types import TracebackType
from typing import Any

from playwright.sync_api import Browser, BrowserContext, Page, Playwright, expect, sync_playwright
from playwright.sync_api import Error as PlaywrightError

from e2e_support.settings import E2ESettings


class BrowserUnavailable(RuntimeError):
    """The configured browser cannot be launched (typically: not installed)."""


class BrowserScenario:
    """The browser state of one scenario: an isolated context and its page.

    Cookies, local storage and permissions never leak from one scenario to the next
    because each scenario gets its own :class:`~playwright.sync_api.BrowserContext`.
    """

    def __init__(self, name: str, context: BrowserContext, page: Page, base_url: str | None):
        self.name = name
        self.context = context
        self.page = page
        self.base_url = base_url

    def close(self) -> None:
        """Close the context (and with it every page it opened)."""
        self.context.close()


class BrowserSession:
    """Owns the Playwright driver and the browser for a whole run.

    Starting a browser is slow, so the session is created once and every scenario
    borrows a fresh context with :meth:`new_scenario`.
    """

    def __init__(self, settings: E2ESettings | None = None) -> None:
        self.settings = settings or E2ESettings.from_env()
        self._playwright: Playwright | None = None
        self._browser: Browser | None = None

    @property
    def browser(self) -> Browser:
        if self._browser is None:
            raise RuntimeError("the browser session is not started")
        return self._browser

    @property
    def is_started(self) -> bool:
        return self._browser is not None

    def start(self) -> BrowserSession:
        """Start the Playwright driver and launch the configured browser.

        Raises :class:`BrowserUnavailable` with the command that installs the browser
        when it cannot be launched.
        """
        if self._browser is not None:
            return self
        self._playwright = sync_playwright().start()
        try:
            engine = getattr(self._playwright, self.settings.browser)
            self._browser = engine.launch(
                headless=self.settings.headless, slow_mo=self.settings.slowmo
            )
        except PlaywrightError as exc:
            self.stop()
            raise BrowserUnavailable(self._explain(exc)) from exc
        expect.set_options(timeout=self.settings.timeout)
        return self

    def stop(self) -> None:
        """Close the browser and stop the Playwright driver. Safe to call twice."""
        browser, playwright = self._browser, self._playwright
        self._browser = self._playwright = None
        try:
            if browser is not None:
                browser.close()
        finally:
            if playwright is not None:
                playwright.stop()

    def new_scenario(
        self, name: str, base_url: str | None = None, **context_options: Any
    ) -> BrowserScenario:
        """Open an isolated context with one page.

        ``base_url`` makes relative navigation (``page.goto("/login")``) work;
        ``context_options`` are passed to :meth:`~playwright.sync_api.Browser.new_context`.
        """
        context = self.browser.new_context(base_url=base_url, **context_options)
        context.set_default_timeout(self.settings.timeout)
        page = context.new_page()
        return BrowserScenario(name, context, page, base_url)

    def __enter__(self) -> BrowserSession:
        return self.start()

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.stop()

    def _explain(self, exc: PlaywrightError) -> str:
        engine = self.settings.browser
        first_line = str(exc).strip().splitlines()[0] if str(exc).strip() else "launch failed"
        hint = f"install it with: python -m playwright install {engine}"
        if "executable doesn't exist" in str(exc).lower():
            return f"the {engine} browser is not installed ({hint})"
        return f"cannot launch {engine}: {first_line} ({hint}, or set E2E_SKIP_BROWSER=1)"
