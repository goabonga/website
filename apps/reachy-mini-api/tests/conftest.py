# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Shared test fixtures for Reachy Mini API tests."""

import os

# Set OAUTH2_ISSUER before any application module is imported, so that the
# OAuth2 scheme is created and Depends(oauth2_scheme) works.
os.environ.setdefault("OAUTH2_ISSUER", "https://auth.test.example.com")
