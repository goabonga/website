# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Step definitions specific to auth.feature scenarios.

These steps handle OAuth2 login/callback/logout/refresh flows.
They mock httpx.AsyncClient rather than using the standard auth mocking,
because these routes ARE the authentication implementation.

NOTE: The basic Given steps (I am authenticated, etc.) live in auth_steps.py.
This file contains When/Then steps specific to the auth feature.
"""

import contextlib
from unittest.mock import AsyncMock, MagicMock, patch

from behave import given, then, when
from httpx import ASGITransport, AsyncClient

# ==========================================================================
# Given steps - httpx mocking
# ==========================================================================


@given("the OAuth2 token endpoint returns valid tokens")
def step_oauth2_tokens_valid(context):
    mock_token_response = MagicMock()
    mock_token_response.status_code = 200
    mock_token_response.json.return_value = {
        "access_token": "new-access-token",
        "refresh_token": "new-refresh-token",
        "expires_in": 3600,
        "token_type": "Bearer",
    }
    mock_token_response.text = '{"access_token":"new-access-token"}'

    mock_client = AsyncMock()
    mock_client.post.return_value = mock_token_response
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    context._httpx_patcher = patch(
        "internal.routes.auth.httpx.AsyncClient", return_value=mock_client
    )
    context._httpx_patcher.start()
    context.mock_httpx_client = mock_client


@given("the OAuth2 userinfo endpoint returns user data")
def step_oauth2_userinfo(context):
    # The callback makes two httpx.AsyncClient() calls:
    # 1. POST to token endpoint
    # 2. GET to userinfo endpoint
    # We need the mock to handle both. Since we create a new AsyncClient for
    # each call, we need to make the factory return different mocks.
    mock_userinfo_response = MagicMock()
    mock_userinfo_response.status_code = 200
    mock_userinfo_response.json.return_value = {
        "sub": "user-123",
        "name": "Test User",
        "email": "test@test.com",
        "picture": "https://example.com/avatar.jpg",
    }

    # The token mock was already set up. Now we need a second mock for userinfo.
    # The callback creates two separate AsyncClient instances.
    # We make the factory return different mocks for each call.
    token_response = MagicMock()
    token_response.status_code = 200
    token_response.json.return_value = {
        "access_token": "new-access-token",
        "refresh_token": "new-refresh-token",
        "expires_in": 3600,
        "token_type": "Bearer",
    }
    token_response.text = '{"access_token":"new-access-token"}'

    # First call returns token client, second call returns userinfo client
    token_client = AsyncMock()
    token_client.post.return_value = token_response
    token_client.__aenter__ = AsyncMock(return_value=token_client)
    token_client.__aexit__ = AsyncMock(return_value=False)

    userinfo_client = AsyncMock()
    userinfo_client.get.return_value = mock_userinfo_response
    userinfo_client.__aenter__ = AsyncMock(return_value=userinfo_client)
    userinfo_client.__aexit__ = AsyncMock(return_value=False)

    # Stop previous patcher if any
    if hasattr(context, "_httpx_patcher"):
        context._httpx_patcher.stop()

    # Return different clients for sequential calls
    context._httpx_patcher = patch(
        "internal.routes.auth.httpx.AsyncClient",
        side_effect=[token_client, userinfo_client],
    )
    context._httpx_patcher.start()
    context.mock_httpx_client = token_client


@given("the OAuth2 token endpoint returns an error")
def step_oauth2_token_error(context):
    mock_response = MagicMock()
    mock_response.status_code = 400
    mock_response.text = '{"error":"invalid_grant","error_description":"Code expired"}'
    mock_response.json.return_value = {
        "error": "invalid_grant",
        "error_description": "Code expired",
    }

    mock_client = AsyncMock()
    mock_client.post.return_value = mock_response
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    context._httpx_patcher = patch(
        "internal.routes.auth.httpx.AsyncClient", return_value=mock_client
    )
    context._httpx_patcher.start()
    context.mock_httpx_client = mock_client


@given("the OAuth2 token endpoint returns valid tokens for refresh")
def step_oauth2_tokens_for_refresh(context):
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "access_token": "refreshed-access-token",
        "refresh_token": "refreshed-refresh-token",
        "expires_in": 3600,
        "token_type": "Bearer",
    }

    mock_client = AsyncMock()
    mock_client.post.return_value = mock_response
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    context._httpx_patcher = patch(
        "internal.routes.auth.httpx.AsyncClient", return_value=mock_client
    )
    context._httpx_patcher.start()
    context.mock_httpx_client = mock_client


@given("the OAuth2 token endpoint rejects the refresh token")
def step_oauth2_refresh_rejected(context):
    mock_response = MagicMock()
    mock_response.status_code = 400
    mock_response.text = '{"error":"invalid_grant"}'
    mock_response.json.return_value = {"error": "invalid_grant"}

    mock_client = AsyncMock()
    mock_client.post.return_value = mock_response
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    context._httpx_patcher = patch(
        "internal.routes.auth.httpx.AsyncClient", return_value=mock_client
    )
    context._httpx_patcher.start()
    context.mock_httpx_client = mock_client


# ==========================================================================
# When steps - OAuth2 callback variations
# ==========================================================================


@when("I complete the OAuth2 callback with valid state")
def step_oauth2_callback_valid(context):
    async def _request():
        async with AsyncClient(
            transport=ASGITransport(app=context.app),
            base_url="http://test",
            cookies={
                "oauth_state": "test-state",
                "oauth_redirect": "/",
                "oauth_code_verifier": "test-verifier",
            },
            follow_redirects=False,
        ) as client:
            return await client.get("/auth/callback?code=test-code&state=test-state")

    context.response = context.loop.run_until_complete(_request())
    # Clean up httpx patcher
    _stop_httpx_patcher(context)


@when('I send an OAuth2 callback with error "{error}" and description "{description}"')
def step_oauth2_callback_error(context, error, description):
    async def _request():
        async with AsyncClient(
            transport=ASGITransport(app=context.app),
            base_url="http://test",
            cookies={
                "oauth_state": "test-state",
                "oauth_redirect": "/",
                "oauth_code_verifier": "test-verifier",
            },
            follow_redirects=False,
        ) as client:
            return await client.get(f"/auth/callback?error={error}&error_description={description}")

    context.response = context.loop.run_until_complete(_request())


@when("I send an OAuth2 callback without code")
def step_oauth2_callback_no_code(context):
    async def _request():
        async with AsyncClient(
            transport=ASGITransport(app=context.app),
            base_url="http://test",
            cookies={
                "oauth_state": "test-state",
                "oauth_redirect": "/",
                "oauth_code_verifier": "test-verifier",
            },
            follow_redirects=False,
        ) as client:
            return await client.get("/auth/callback?state=test-state")

    context.response = context.loop.run_until_complete(_request())


@when("I send an OAuth2 callback with mismatched state")
def step_oauth2_callback_bad_state(context):
    async def _request():
        async with AsyncClient(
            transport=ASGITransport(app=context.app),
            base_url="http://test",
            cookies={
                "oauth_state": "original-state",
                "oauth_redirect": "/",
                "oauth_code_verifier": "test-verifier",
            },
            follow_redirects=False,
        ) as client:
            return await client.get("/auth/callback?code=test-code&state=different-state")

    context.response = context.loop.run_until_complete(_request())


@when("I send an OAuth2 callback without state cookie")
def step_oauth2_callback_no_state_cookie(context):
    async def _request():
        async with AsyncClient(
            transport=ASGITransport(app=context.app),
            base_url="http://test",
            cookies={},
            follow_redirects=False,
        ) as client:
            return await client.get("/auth/callback?code=test-code&state=test-state")

    context.response = context.loop.run_until_complete(_request())


@when("I send an OAuth2 callback without code verifier cookie")
def step_oauth2_callback_no_verifier(context):
    async def _request():
        async with AsyncClient(
            transport=ASGITransport(app=context.app),
            base_url="http://test",
            cookies={
                "oauth_state": "test-state",
                "oauth_redirect": "/",
            },
            follow_redirects=False,
        ) as client:
            return await client.get("/auth/callback?code=test-code&state=test-state")

    context.response = context.loop.run_until_complete(_request())


@when("I send a refresh request with a valid refresh token")
def step_refresh_with_token(context):
    async def _request():
        async with AsyncClient(
            transport=ASGITransport(app=context.app),
            base_url="http://test",
            cookies={
                "refresh_token": "existing-refresh-token",
            },
            follow_redirects=False,
        ) as client:
            return await client.get("/auth/refresh")

    context.response = context.loop.run_until_complete(_request())
    # Clean up httpx patcher
    _stop_httpx_patcher(context)


# ==========================================================================
# Then steps - cookie assertions
# ==========================================================================


@then('the response should set cookie "{cookie_name}"')
def step_check_cookie_set(context, cookie_name):
    set_cookies = context.response.headers.get_list("set-cookie")
    found = any(cookie_name in sc for sc in set_cookies)
    assert found, f"Expected cookie '{cookie_name}' to be set. Set-Cookie headers: {set_cookies}"


@then('the response should delete cookie "{cookie_name}"')
def step_check_cookie_deleted(context, cookie_name):
    set_cookies = context.response.headers.get_list("set-cookie")
    # A deleted cookie has max-age=0 or expires in the past
    found = any(
        cookie_name in sc and ("max-age=0" in sc.lower() or '="";' in sc or "='';")
        for sc in set_cookies
    )
    # Also check for the cookie name with empty value or max-age=0 pattern
    if not found:
        found = any(
            f'{cookie_name}=""' in sc or f'{cookie_name}=""; ' in sc or f"{cookie_name}=;" in sc
            for sc in set_cookies
        )
    assert found, (
        f"Expected cookie '{cookie_name}' to be deleted. Set-Cookie headers: {set_cookies}"
    )


# ==========================================================================
# Helper functions
# ==========================================================================


def _stop_httpx_patcher(context):
    """Stop the httpx patcher if it was started."""
    patcher = getattr(context, "_httpx_patcher", None)
    if patcher is not None:
        with contextlib.suppress(RuntimeError):
            patcher.stop()
