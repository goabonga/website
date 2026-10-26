# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Behave environment hooks.

Scenarios run entirely in-process: no network, no PostgreSQL (an in-memory session
replaces it), no Redis, no Step-CA and no OpenVPN server.
"""

import asyncio
import os
import sys
from pathlib import Path

# The in-memory database session lives with the pytest helpers; the hook script lives in scripts/.
APP_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(APP_DIR / "tests"))
sys.path.insert(0, str(APP_DIR))

# The OAuth2 scheme is built when the application is imported.
os.environ.setdefault("OAUTH2_ISSUER", "https://auth.test.example.com")

from fake_session import FakeSession  # noqa: E402
from vpn_portal.db.session import get_db  # noqa: E402
from vpn_portal.main import app  # noqa: E402


def before_scenario(context, scenario):
    """Give every scenario its own event loop, exposed as ``context.run``."""
    context.loop = asyncio.new_event_loop()
    asyncio.set_event_loop(context.loop)
    context.run = context.loop.run_until_complete
    context.app = app
    context.db = FakeSession()

    async def override_get_db():
        yield context.db

    app.dependency_overrides[get_db] = override_get_db
    context.headers = {}
    context.response = None


def after_scenario(context, scenario):
    """Drop the database override and close the scenario event loop."""
    app.dependency_overrides.clear()
    context.loop.close()
