# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Fixtures of the browser tests; they skip cleanly when no browser can run."""

import pytest
from e2e_support.browser import BrowserSession, BrowserUnavailable
from e2e_support.server import LiveServer
from e2e_support.settings import E2ESettings
from toy_site import site as toy_site


@pytest.fixture(scope="session")
def e2e_settings() -> E2ESettings:
    return E2ESettings.from_env()


@pytest.fixture(scope="session")
def browser_session(e2e_settings):
    """One browser for the whole test run; skips the test if none can start."""
    if e2e_settings.skip_browser:
        pytest.skip("E2E_SKIP_BROWSER is set")
    session = BrowserSession(e2e_settings)
    try:
        session.start()
    except BrowserUnavailable as exc:
        pytest.skip(str(exc))
    yield session
    session.stop()


@pytest.fixture(scope="session")
def site():
    """The tiny ASGI site served on a real port."""
    with LiveServer(toy_site) as server:
        yield server
