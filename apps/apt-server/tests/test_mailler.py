# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Client of the internal mailler service."""

import json

import httpx
import pytest
from apt_server.config import settings
from apt_server.services import mailler

REAL_ASYNC_CLIENT = httpx.AsyncClient


@pytest.fixture(autouse=True)
def mailler_settings(monkeypatch):
    monkeypatch.setattr(settings, "email_backend", "mailler")
    monkeypatch.setattr(settings, "mailler_client_id", "cid")
    monkeypatch.setattr(settings, "mailler_client_secret", "csecret")
    monkeypatch.setattr(settings, "mailler_auth_url", "https://auth.example/")
    monkeypatch.setattr(settings, "mailler_url", "http://mailler.local")
    monkeypatch.setattr(settings, "mailler_unix_socket", "")
    monkeypatch.setattr(settings, "mailler_provider", "brevo")
    monkeypatch.setattr(settings, "email_from", "noreply@example.com")
    monkeypatch.setattr(settings, "email_from_name", "APT Server")
    monkeypatch.setattr(mailler, "_cached_token", "")
    monkeypatch.setattr(mailler, "_token_expires_at", 0)


@pytest.fixture
def mailler_service(monkeypatch):
    state = {"token_status": 200, "send_status": 202, "requests": []}

    def handler(request: httpx.Request) -> httpx.Response:
        state["requests"].append(request)
        if request.url.path == "/oauth2/token":
            if state["token_status"] != 200:
                return httpx.Response(state["token_status"])
            return httpx.Response(200, json={"access_token": "mailer-token", "expires_in": 3600})
        if request.url.path == "/api/v1/send":
            if state["send_status"] == 0:
                raise httpx.ConnectError("down")
            return httpx.Response(state["send_status"], text="body")
        return httpx.Response(404)

    monkeypatch.setattr(
        mailler.httpx,
        "AsyncClient",
        lambda **kwargs: REAL_ASYNC_CLIENT(
            transport=httpx.MockTransport(handler),
            **{k: v for k, v in kwargs.items() if k != "transport"},
        ),
    )
    return state


def paths(state) -> list[str]:
    return [r.url.path for r in state["requests"]]


async def send(**overrides):
    values = {
        "to_email": "bob@example.com",
        "to_name": "Bob",
        "subject": "Hi",
        "html_content": "<p>x</p>",
    }
    await mailler.send_email(**{**values, **overrides})


async def test_send_posts_the_message_with_a_client_credentials_token(mailler_service) -> None:
    await send(text_content="plain")

    token_request, send_request = mailler_service["requests"]
    assert str(token_request.url) == "https://auth.example/oauth2/token"
    assert b"grant_type=client_credentials" in token_request.content
    assert b"scope=mailler%3Asend" in token_request.content
    assert send_request.headers["Authorization"] == "Bearer mailer-token"
    body = json.loads(send_request.content)
    assert body["to_email"] == "bob@example.com"
    assert body["subject"] == "Hi"
    assert body["text_content"] == "plain"
    assert body["from_email"] == "noreply@example.com"
    assert body["provider"] == "brevo"
    assert body["metadata"] == {"source": "apt-server"}


async def test_text_content_is_null_when_absent(mailler_service) -> None:
    await send()

    assert json.loads(mailler_service["requests"][1].content)["text_content"] is None


async def test_the_token_is_reused_until_it_expires(mailler_service, monkeypatch) -> None:
    await send()
    await send()

    assert paths(mailler_service) == ["/oauth2/token", "/api/v1/send", "/api/v1/send"]

    monkeypatch.setattr(mailler, "_token_expires_at", 0)
    await send()
    assert paths(mailler_service).count("/oauth2/token") == 2


async def test_auth_url_defaults_to_the_oauth2_issuer(mailler_service, monkeypatch) -> None:
    monkeypatch.setattr(settings, "mailler_auth_url", "")
    monkeypatch.setattr(settings, "oauth2_issuer", "https://issuer.example")

    await send()

    assert str(mailler_service["requests"][0].url) == "https://issuer.example/oauth2/token"


async def test_nothing_is_sent_when_the_backend_is_disabled(mailler_service, monkeypatch) -> None:
    monkeypatch.setattr(settings, "email_backend", "")

    await send()

    assert mailler_service["requests"] == []


async def test_nothing_is_sent_without_credentials(mailler_service, monkeypatch) -> None:
    monkeypatch.setattr(settings, "mailler_client_secret", "")

    await send()

    assert mailler_service["requests"] == []


async def test_authentication_failure_is_swallowed(mailler_service) -> None:
    mailler_service["token_status"] = 401

    await send()

    assert paths(mailler_service) == ["/oauth2/token"]


@pytest.mark.parametrize("status", [0, 500])
async def test_send_failures_never_raise(mailler_service, status) -> None:
    mailler_service["send_status"] = status

    await send()

    assert paths(mailler_service)[-1] == "/api/v1/send"


def test_unix_socket_transport_is_used_when_configured(monkeypatch) -> None:
    assert mailler._transport() is None

    monkeypatch.setattr(settings, "mailler_unix_socket", "/run/mailler/mailler.sock")

    assert isinstance(mailler._transport(), httpx.AsyncHTTPTransport)
