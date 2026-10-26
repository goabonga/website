# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Behave environment of the worked example: a toy application and a fake OpenID provider."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from e2e_support import behave_hooks as e2e  # noqa: E402
from e2e_support.oidc import Client, FakeOIDCProvider, User  # noqa: E402
from toy_oidc_app import ToyConfig, create_app  # noqa: E402

SERVICE_SCOPES = ("openid", "profile", "email", "billing:*", "introspect")


def start_stack(context, scenario):
    """Serve the provider and the application once per run, and reset the provider."""
    servers = context.e2e.servers
    if "provider" not in servers:
        config = ToyConfig()
        provider = FakeOIDCProvider(
            users=[
                User(
                    email="ada@example.test",
                    name="Ada",
                    password="secret",
                    scopes=("billing:read",),
                ),
                User(email="grace@example.test", name="Grace", password="secret"),
            ],
            clients=[
                Client.service(
                    config.service_client_id, config.service_client_secret, SERVICE_SCOPES
                )
            ],
        )
        config.issuer = e2e.live_server(context, "provider", provider).url
        config.base_url = e2e.live_server(context, "app", create_app(config)).url
        provider.add_client(Client.public(config.client_id, [f"{config.base_url}/auth/callback"]))

    provider = servers["provider"].app
    provider.end_sessions()
    provider.revoke_tokens()
    provider.clear_requests()
    provider.auto_approve = "auto-approve" in scenario.effective_tags
    return servers["app"].url


def before_all(context):
    e2e.before_all(context)


def before_scenario(context, scenario):
    e2e.before_scenario(context, scenario, base_url=lambda: start_stack(context, scenario))


def after_scenario(context, scenario):
    e2e.after_scenario(context, scenario)


def after_all(context):
    e2e.after_all(context)
