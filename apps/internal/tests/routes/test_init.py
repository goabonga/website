# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for internal/routes/__init__.py - router imports and re-exports."""


class TestAllRoutersImportable:
    def test_admin_router(self):
        from internal.routes import admin_router

        assert admin_router is not None

    def test_analytics_router(self):
        from internal.routes import analytics_router

        assert analytics_router is not None

    def test_auth_router(self):
        from internal.routes import auth_router

        assert auth_router is not None

    def test_billing_router(self):
        from internal.routes import billing_router

        assert billing_router is not None

    def test_contacts_router(self):
        from internal.routes import contacts_router

        assert contacts_router is not None

    def test_mailler_router(self):
        from internal.routes import mailler_router

        assert mailler_router is not None

    def test_team_router(self):
        from internal.routes import team_router

        assert team_router is not None

    def test_vpn_router(self):
        from internal.routes import vpn_router

        assert vpn_router is not None

    def test_all_exports(self):
        from internal.routes import __all__

        expected = [
            "admin_router",
            "analytics_router",
            "auth_router",
            "billing_router",
            "contacts_router",
            "mailler_router",
            "team_router",
            "vpn_router",
        ]
        assert set(expected) <= set(__all__)

    def test_all_exports_count(self):
        from internal.routes import __all__

        assert len(__all__) >= 8
