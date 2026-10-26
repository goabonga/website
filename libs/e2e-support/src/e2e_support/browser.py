# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Playwright session management: one browser per run, one context per scenario."""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path
from types import TracebackType
from typing import Any

from playwright.sync_api import Browser, BrowserContext, Page, Playwright, expect, sync_playwright
from playwright.sync_api import Error as PlaywrightError

from e2e_support.diagnostics import (
    Diagnostics,
    save_failure_artifacts,
    save_screenshots,
    slugify,
)
from e2e_support.settings import E2ESettings


class BrowserUnavailable(RuntimeError):
    """The configured browser cannot be launched (typically: not installed)."""


class BrowserScenario:
    """The browser state of one scenario: an isolated context and its page.

    Cookies, local storage and permissions never leak from one scenario to the next
    because each scenario gets its own :class:`~playwright.sync_api.BrowserContext`.
    ``diagnostics`` records what the browser reported (console, page errors) and
    :meth:`finish` keeps a screenshot, a trace and the page HTML when the scenario failed.
    """

    def __init__(
        self,
        name: str,
        context: BrowserContext,
        page: Page,
        base_url: str | None,
        settings: E2ESettings,
        artifacts: Path,
    ):
        self.name = name
        self.context = context
        self.page = page
        self.base_url = base_url
        self.settings = settings
        self.artifacts = artifacts
        self.diagnostics = Diagnostics(context)
        self._steps = 0
        self._last_step_image: bytes | None = None
        if settings.trace:
            context.tracing.start(screenshots=True, snapshots=True)

    def assert_no_browser_errors(self, ignore: Iterable[str] = ()) -> None:
        """Fail if a console error or an uncaught page error was reported."""
        self.diagnostics.assert_clean(ignore)

    def capture_step(self, text: str) -> Path | None:
        """Screenshot the page as it is after a step, numbered in execution order.

        The files go to ``<artifacts dir>/<scenario>/steps/``. Nothing is kept (``None``)
        while the page is still blank (no navigation yet), when it looks exactly like the
        previous capture, or when it crashed or closed: a screenshot never fails a
        scenario. The number is that of the step, so a gap means "nothing new to see".
        """
        self._steps += 1
        try:
            if self.page.url == "about:blank":
                return None
            image = self.page.screenshot(full_page=True)
        except PlaywrightError:
            return None
        if image == self._last_step_image:
            return None
        self._last_step_image = image
        directory = self.artifacts / "steps"
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / f"{self._steps:02d}-{slugify(text)}.png"
        path.write_bytes(image)
        return path

    def finish(self, failed: bool = False) -> list[Path]:
        """End the scenario and close its context.

        When ``failed`` is true, ``<artifacts dir>/<scenario>/`` receives ``screenshot.png``,
        ``page.html``, ``console.log`` and, unless ``E2E_TRACE`` is off, ``trace.zip``.
        When ``E2E_SCREENSHOTS`` is ``scenario`` or ``steps``, a scenario that passed keeps
        a ``screenshot.png`` of its pages there too. Returns the saved files (empty when a passed scenario
        needs none).
        """
        saved: list[Path] = []
        try:
            if failed:
                saved = save_failure_artifacts(self.artifacts, self.context, self.diagnostics)
            elif self.settings.screenshots != "off":
                saved = save_screenshots(self.artifacts, self.context)
            if self.settings.trace:
                if failed:
                    trace = self.artifacts / "trace.zip"
                    self.context.tracing.stop(path=trace)
                    saved.append(trace)
                else:
                    self.context.tracing.stop()
        finally:
            self.context.close()
        return saved

    def close(self) -> None:
        """Close the context of a scenario that passed."""
        self.finish(failed=False)


class BrowserSession:
    """Owns the Playwright driver and the browser for a whole run.

    Starting a browser is slow, so the session is created once and every scenario
    borrows a fresh context with :meth:`new_scenario`.
    """

    def __init__(self, settings: E2ESettings | None = None) -> None:
        self.settings = settings or E2ESettings.from_env()
        self._playwright: Playwright | None = None
        self._browser: Browser | None = None
        self._artifact_names: set[str] = set()

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
        return BrowserScenario(
            name, context, page, base_url, self.settings, self._artifacts_for(name)
        )

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

    def _artifacts_for(self, name: str) -> Path:
        """A directory of its own for the artifacts of the scenario ``name``."""
        slug = slugify(name)
        candidate, counter = slug, 1
        while candidate in self._artifact_names:
            counter += 1
            candidate = f"{slug}-{counter}"
        self._artifact_names.add(candidate)
        return self.settings.artifacts_dir / candidate
