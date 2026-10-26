# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Worked example: an application that logs in through OpenID Connect, in a real browser."""

from pathlib import Path

import pytest
from e2e_support.oidc import Client, FakeOIDCProvider, SigningKey, User
from e2e_support.server import LiveServer
from test_behave_hooks import run_behave
from toy_oidc_app import ToyConfig, create_app

PROJECT = Path(__file__).parent / "behave_oidc_project" / "features"
KEY = SigningKey()


@pytest.fixture
def stack():
    """The provider and the toy application, wired together."""
    config = ToyConfig()
    provider = FakeOIDCProvider(
        users=[
            User(email="ada@example.test", name="Ada", password="secret", scopes=("billing:read",))
        ],
        clients=[
            Client.service(
                config.service_client_id,
                config.service_client_secret,
                ["openid", "profile", "email", "billing:*", "introspect"],
            )
        ],
        signing_key=KEY,
    )
    with LiveServer(provider) as provider_server:
        config.issuer = provider_server.url
        with LiveServer(create_app(config)) as app_server:
            config.base_url = app_server.url
            provider.add_client(
                Client.public(config.client_id, [f"{app_server.url}/auth/callback"])
            )
            yield provider, app_server


@pytest.mark.browser
def test_a_user_logs_in_through_the_provider(browser_session, stack):
    provider, app = stack
    scenario = browser_session.new_scenario("oidc example", base_url=app.url)
    page = scenario.page
    try:
        page.goto("/dashboard")
        assert "/oauth2/authorize" in page.url
        page.get_by_label("Email").fill("ada@example.test")
        page.get_by_label("Password").fill("secret")
        page.get_by_role("button", name="Sign in").click()
        page.wait_for_url(f"{app.url}/dashboard")
        assert page.get_by_role("heading", name="Welcome Ada").is_visible()
        assert page.get_by_role("link", name="Billing").is_visible()
        scenario.assert_no_browser_errors()
    finally:
        scenario.close()
    grants = [r.form["grant_type"] for r in provider.requests_to("/oauth2/token")]
    assert grants == ["authorization_code", "urn:ietf:params:oauth:grant-type:token-exchange"]


@pytest.mark.browser
def test_the_behave_example_passes(browser_session, tmp_path):
    process, counts = run_behave(tmp_path, features=("login.feature",), project=PROJECT)
    assert process.returncode == 0, process.stdout + process.stderr
    assert counts == {"passed": 8, "failed": 0, "skipped": 0}
