# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Browser test settings, read from ``E2E_*`` environment variables."""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

#: Browser engines Playwright can launch.
SUPPORTED_BROWSERS = ("chromium", "firefox", "webkit")

_TRUE = frozenset({"1", "true", "yes", "on"})
_FALSE = frozenset({"0", "false", "no", "off", ""})


class SettingsError(ValueError):
    """An ``E2E_*`` variable holds an unusable value."""


def _flag(environ: Mapping[str, str], name: str, default: bool) -> bool:
    raw = environ.get(name)
    if raw is None:
        return default
    value = raw.strip().lower()
    if value in _TRUE:
        return True
    if value in _FALSE:
        return False
    raise SettingsError(f"{name}={raw!r} is not a boolean (use 1/0, true/false, yes/no, on/off)")


#: What ``E2E_SCREENSHOTS`` can keep for the scenarios that passed.
SCREENSHOT_MODES = ("off", "scenario", "steps")


def _screenshots(environ: Mapping[str, str], name: str, default: str) -> str:
    raw = environ.get(name)
    if raw is None:
        return default
    value = raw.strip().lower()
    if value in _FALSE:
        return "off"
    if value in _TRUE:
        return "scenario"
    if value in SCREENSHOT_MODES:
        return value
    raise SettingsError(
        f"{name}={raw!r} is not a screenshot mode (use off, scenario or steps, or a boolean)"
    )


def _integer(environ: Mapping[str, str], name: str, default: int, minimum: int = 0) -> int:
    raw = environ.get(name)
    if raw is None or not raw.strip():
        return default
    try:
        value = int(raw)
    except ValueError:
        raise SettingsError(f"{name}={raw!r} is not an integer") from None
    if value < minimum:
        raise SettingsError(f"{name}={raw!r} must be at least {minimum}")
    return value


@dataclass(frozen=True)
class E2ESettings:
    """How browser scenarios run.

    Every field has an ``E2E_<NAME>`` environment variable (see :meth:`from_env`).
    """

    browser: str = "chromium"
    headless: bool = True
    slowmo: int = 0
    artifacts_dir: Path = Path("artifacts")
    skip_browser: bool = False
    timeout: int = 10_000
    trace: bool = True
    screenshots: str = "off"

    @classmethod
    def from_env(cls, environ: Mapping[str, str] | None = None) -> E2ESettings:
        """Build the settings from ``environ`` (``os.environ`` by default)."""
        env = os.environ if environ is None else environ
        defaults = cls()
        browser = env.get("E2E_BROWSER", defaults.browser).strip().lower()
        if browser not in SUPPORTED_BROWSERS:
            raise SettingsError(
                f"E2E_BROWSER={browser!r} is not supported "
                f"(choose one of {', '.join(SUPPORTED_BROWSERS)})"
            )
        artifacts = env.get("E2E_ARTIFACTS_DIR", "").strip()
        return cls(
            browser=browser,
            headless=_flag(env, "E2E_HEADLESS", defaults.headless),
            slowmo=_integer(env, "E2E_SLOWMO", defaults.slowmo),
            artifacts_dir=Path(artifacts) if artifacts else defaults.artifacts_dir,
            skip_browser=_flag(env, "E2E_SKIP_BROWSER", defaults.skip_browser),
            timeout=_integer(env, "E2E_TIMEOUT", defaults.timeout, minimum=1),
            trace=_flag(env, "E2E_TRACE", defaults.trace),
            screenshots=_screenshots(env, "E2E_SCREENSHOTS", defaults.screenshots),
        )
