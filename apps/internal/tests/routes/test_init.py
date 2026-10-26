# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for internal/routes/__init__.py - router imports and re-exports."""


class TestAllRoutersImportable:
    def test_auth_router(self):
        from internal.routes import auth_router

        assert auth_router is not None

    def test_all_exports(self):
        from internal.routes import __all__

        expected = [
            "auth_router",
        ]
        assert set(expected) <= set(__all__)

    def test_all_exports_count(self):
        from internal.routes import __all__

        assert len(__all__) >= 1
