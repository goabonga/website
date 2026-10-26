# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""What the browser reported while a scenario ran, and what is kept when it fails."""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

from playwright.sync_api import BrowserContext
from playwright.sync_api import Error as PlaywrightError

#: Console message types that count as errors for :meth:`Diagnostics.assert_clean`.
ERROR_TYPES = ("error",)


@dataclass(frozen=True)
class Entry:
    """One thing the page reported: a console message or an uncaught page error."""

    kind: str  # "console" or "pageerror"
    level: str  # console message type ("log", "warning", "error", ...) or "error"
    text: str
    location: str = ""

    @property
    def is_error(self) -> bool:
        return self.level in ERROR_TYPES

    def __str__(self) -> str:
        where = f" ({self.location})" if self.location else ""
        return f"[{self.kind}:{self.level}] {self.text}{where}"


class Diagnostics:
    """Collects console messages and uncaught page errors of every page of a context."""

    def __init__(self, context: BrowserContext) -> None:
        self.entries: list[Entry] = []
        context.on("console", self._on_console)
        context.on("weberror", self._on_web_error)

    @property
    def errors(self) -> list[Entry]:
        """Console errors and uncaught page errors."""
        return [entry for entry in self.entries if entry.is_error]

    def clear(self) -> None:
        self.entries.clear()

    def assert_clean(self, ignore: Iterable[str] = ()) -> None:
        """Fail when the browser reported an error.

        ``ignore`` holds regular expressions; an error whose text matches one of them
        (``re.search``) is tolerated, for example ``r"favicon\\.ico"``.
        """
        patterns = [re.compile(pattern) for pattern in ignore]
        failures = [
            entry
            for entry in self.errors
            if not any(pattern.search(entry.text) for pattern in patterns)
        ]
        if failures:
            listing = "\n".join(f"  - {entry}" for entry in failures)
            raise AssertionError(f"the browser reported {len(failures)} error(s):\n{listing}")

    def render(self) -> str:
        """The collected entries, one per line, for the saved console log."""
        return "\n".join(str(entry) for entry in self.entries) + ("\n" if self.entries else "")

    def _on_console(self, message) -> None:
        location = message.location or {}
        url = location.get("url", "")
        line = location.get("lineNumber")
        where = f"{url}:{line}" if url and line is not None else url
        self.entries.append(Entry("console", message.type, message.text, where))

    def _on_web_error(self, web_error) -> None:
        self.entries.append(Entry("pageerror", "error", str(web_error.error)))


def slugify(name: str) -> str:
    """A file-system safe version of a scenario name."""
    slug = re.sub(r"-{2,}", "-", re.sub(r"[^A-Za-z0-9._-]+", "-", name)).strip("-.")
    return slug[:100] or "scenario"


def save_screenshots(directory: Path, context: BrowserContext) -> list[Path]:
    """Write a full-page screenshot of every open page of ``context``.

    Like :func:`save_failure_artifacts`, a page that crashed or closed is skipped.
    """
    directory.mkdir(parents=True, exist_ok=True)
    saved: list[Path] = []
    for index, page in enumerate(context.pages):
        suffix = "" if index == 0 else f"-{index + 1}"
        try:
            screenshot = directory / f"screenshot{suffix}.png"
            page.screenshot(path=screenshot, full_page=True)
            saved.append(screenshot)
        except PlaywrightError:
            pass
    return saved


def save_failure_artifacts(
    directory: Path, context: BrowserContext, diagnostics: Diagnostics
) -> list[Path]:
    """Write a screenshot and the HTML of every open page, and the console log.

    Capturing never raises: a page that crashed or closed is skipped, because the
    artifacts must not hide the failure they describe.
    """
    directory.mkdir(parents=True, exist_ok=True)
    saved: list[Path] = []
    for index, page in enumerate(context.pages):
        suffix = "" if index == 0 else f"-{index + 1}"
        try:
            screenshot = directory / f"screenshot{suffix}.png"
            page.screenshot(path=screenshot, full_page=True)
            saved.append(screenshot)
        except PlaywrightError:
            pass
        try:
            html = directory / f"page{suffix}.html"
            html.write_text(f"<!-- {page.url} -->\n{page.content()}", encoding="utf-8")
            saved.append(html)
        except PlaywrightError:
            pass
    log = directory / "console.log"
    log.write_text(diagnostics.render(), encoding="utf-8")
    saved.append(log)
    return saved
