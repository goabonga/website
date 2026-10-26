# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Steps specific to the foundation feature."""

from behave import then


@then("the service name is configured as apt-server")
def check_service_name(context):
    from apt_server.config import settings

    assert settings.app_name == "apt-server"
