# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Step definitions for hooks.feature.

The hook script runs for real. Its synchronous HTTP client is given a transport that serves
every request in-process through the portal's ASGI application, so the script, the internal
API and the in-memory database are exercised together. The OAuth2 server is a mock.
"""

import json
import os
import tempfile
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import httpx
from behave import given, then, when
from httpx import ASGITransport, AsyncClient

from scripts import openvpn as hook


def _portal_transport(context):
    """Transport that forwards requests to the portal application in-process."""

    def handler(request: httpx.Request) -> httpx.Response:
        async def call():
            async with AsyncClient(
                transport=ASGITransport(app=context.app), base_url="http://portal"
            ) as portal:
                return await portal.request(
                    request.method,
                    request.url.path,
                    content=request.content,
                    headers=dict(request.headers),
                )

        portal_response = context.run(call())
        # Re-wrap: the synchronous client needs a synchronous body stream.
        return httpx.Response(
            portal_response.status_code,
            headers={"content-type": portal_response.headers["content-type"]},
            content=portal_response.content,
        )

    return httpx.MockTransport(handler)


def _environment(context):
    if not hasattr(context, "hook_env"):
        context.hook_env = {}
        context.hook_argv = ["openvpn.py"]
    return context.hook_env


@given(
    'OpenVPN reports the client "{cn}" from "{ip}" with VPN address "{vpn_ip}"',
)
def step_client_connecting(context, cn, ip, vpn_ip):
    _environment(context).update(
        {"common_name": cn, "untrusted_ip": ip, "ifconfig_pool_remote_ip": vpn_ip}
    )


@given('OpenVPN reports the client "{cn}" from "{ip}" on port "{port}"')
def step_client_with_port(context, cn, ip, port):
    _environment(context).update({"common_name": cn, "untrusted_ip": ip, "untrusted_port": port})


@given("OpenVPN reports no common name")
def step_no_common_name(context):
    _environment(context)


@given(
    'OpenVPN reports the client "{cn}" disconnecting after {rx:d} bytes received '
    "and {tx:d} bytes sent"
)
def step_client_disconnecting(context, cn, rx, tx):
    _environment(context).update(
        {"common_name": cn, "bytes_received": str(rx), "bytes_sent": str(tx)}
    )


def _run(context, flag, extra_args=()):
    env = dict(_environment(context))
    workdir = tempfile.TemporaryDirectory()
    context.add_cleanup(workdir.cleanup)
    context.routes_file = Path(workdir.name) / "openvpn_cc_routes"
    argv = ["openvpn.py", flag, *extra_args]
    if flag == "--connect":
        argv.append(str(context.routes_file))

    context.kill = MagicMock()
    with (
        patch.dict(os.environ, env, clear=False),
        patch("sys.argv", argv),
        patch.object(hook, "_kill_client_via_management", context.kill),
        httpx.Client(transport=_portal_transport(context)) as client,
    ):
        handler = {
            "--connect": hook.handle_connect,
            "--disconnect": hook.handle_disconnect,
            "--reneg": hook.handle_reneg,
        }[flag]
        with patch.object(hook, "API_BASE_URL", "http://portal"):
            context.exit_code = handler(client, "any-token")


@when("OpenVPN runs the connect hook")
def step_run_connect(context):
    _run(context, "--connect")


@when("OpenVPN runs the disconnect hook")
def step_run_disconnect(context):
    _run(context, "--disconnect")


@when("OpenVPN runs the renegotiation hook at depth {depth:d}")
def step_run_reneg(context, depth):
    _run(context, "--reneg", (str(depth), "CN=subject"))


@then("the hook should exit with code {code:d}")
def step_exit_code(context, code):
    assert context.exit_code == code, f"exit code {context.exit_code}"


@then("the routes file should contain '{line}'")
def step_routes_file(context, line):
    assert line in context.routes_file.read_text().splitlines()


@then('the client "{address}" should be killed')
def step_killed(context, address):
    context.kill.assert_called_once_with(address)


@then("the client should not be killed")
def step_not_killed(context):
    context.kill.assert_not_called()


# -- access token -------------------------------------------------------------------------


def _use_token_cache(context):
    if hasattr(context, "token_cache"):
        return
    workdir = tempfile.TemporaryDirectory()
    context.add_cleanup(workdir.cleanup)
    context.token_cache = Path(workdir.name) / "token.json"
    for name, value in (
        ("TOKEN_CACHE_PATH", str(context.token_cache)),
        ("CLIENT_ID", "openvpn-hook"),
        ("CLIENT_SECRET", "hook-secret"),
        ("TOKEN_URL", "https://auth.test.example.com/oauth2/token"),
        ("OAUTH2_SCOPE", "vpn:server"),
    ):
        patcher = patch.object(hook, name, value)
        patcher.start()
        context.add_cleanup(patcher.stop)


@given('the OAuth2 server issues the token "{token}" valid for {seconds:d} seconds')
def step_oauth2_issues(context, token, seconds):
    _use_token_cache(context)
    context.oauth2_requests = []

    def handler(request: httpx.Request) -> httpx.Response:
        context.oauth2_requests.append(request)
        return httpx.Response(200, json={"access_token": token, "expires_in": seconds})

    context.oauth2_transport = httpx.MockTransport(handler)


@given("there is no cached token")
def step_no_cached_token(context):
    _use_token_cache(context)
    assert not context.token_cache.exists()


@given('there is a cached token "{token}" valid for {seconds:d} seconds')
def step_cached_token(context, token, seconds):
    _use_token_cache(context)
    context.token_cache.write_text(
        json.dumps({"access_token": token, "expires_at": time.time() + seconds})
    )
    context.oauth2_requests = []
    context.oauth2_transport = httpx.MockTransport(
        lambda request: context.oauth2_requests.append(request) or httpx.Response(500)
    )


@when("the hook requests an access token")
def step_request_token(context):
    with httpx.Client(transport=context.oauth2_transport) as client:
        context.token = hook.get_access_token(client)


@then('the token should be "{token}"')
def step_token(context, token):
    assert context.token == token


@then('the OAuth2 server should have received the "{grant}" grant for scope "{scope}"')
def step_grant(context, grant, scope):
    (request,) = context.oauth2_requests
    form = dict(item.split("=", 1) for item in request.content.decode().split("&"))
    assert form["grant_type"] == grant
    assert form["scope"].replace("%3A", ":") == scope
    assert form["client_id"] == "openvpn-hook"


@then("the OAuth2 server should not have been called")
def step_oauth2_not_called(context):
    assert context.oauth2_requests == []


@then("the token should be cached")
def step_token_cached(context):
    cached = json.loads(context.token_cache.read_text())
    assert cached["access_token"] == context.token
    assert cached["expires_at"] > time.time()


@then('the netmask for prefix {prefix:d} should be "{netmask}"')
def step_netmask(context, prefix, netmask):
    assert hook._cidr_to_netmask(prefix) == netmask
