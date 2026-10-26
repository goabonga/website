# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Conftest for route tests.

Sets OAUTH2_ISSUER before app modules are imported to prevent FastAPI
dependency resolution failure with a None oauth2_scheme on Python 3.13.
This must run before any test module in this directory is collected.
"""

import os

# Must be set before Settings is instantiated.  The root conftest imports
# backend.auth.models which triggers the full backend.auth.__init__ -> config import
# chain, so we set it here via pytest_configure which runs before collection.


def pytest_configure(config):
    os.environ.setdefault("OAUTH2_ISSUER", "https://auth.test.example.com")
