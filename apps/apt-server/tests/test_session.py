# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Signed cookies and PKCE helpers used by the web login."""

import base64
import hashlib
import json
import time

import pytest
from apt_server.config import settings
from apt_server.services import session


@pytest.fixture(autouse=True)
def secrets(monkeypatch):
    monkeypatch.setattr(settings, "session_secret", "s3cret")
    monkeypatch.setattr(settings, "oauth2_client_secret", "")
    monkeypatch.setattr(settings, "session_max_age", 3600)


def test_session_cookie_round_trip() -> None:
    cookie = session.create_session_cookie(
        "tok", display_name="a@example.com", name="Alice", avatar_url="/a.png"
    )

    data = session.read_session_cookie(cookie)

    assert data == session.SessionData(
        token="tok", display_name="a@example.com", name="Alice", avatar_url="/a.png"
    )


def test_session_cookie_defaults_optional_fields() -> None:
    data = session.read_session_cookie(session.create_session_cookie("tok"))

    assert (data.display_name, data.name, data.avatar_url) == ("", "", "")


def test_tampered_cookie_is_rejected() -> None:
    cookie = session.create_session_cookie("tok")
    payload, signature = cookie.split(".")
    forged = base64.urlsafe_b64encode(json.dumps({"token": "evil", "iat": 9**9}).encode()).decode()

    assert session.read_session_cookie(f"{forged}.{signature}") is None
    assert session.read_session_cookie(payload + ".AAAA") is None


@pytest.mark.parametrize("value", ["", "no-dot", "!!!.???", "a.b.c"])
def test_malformed_cookies_are_rejected(value) -> None:
    assert session.read_session_cookie(value) is None


def test_cookie_signed_with_another_secret_is_rejected(monkeypatch) -> None:
    cookie = session.create_session_cookie("tok")
    monkeypatch.setattr(settings, "session_secret", "other")

    assert session.read_session_cookie(cookie) is None


def test_expired_cookie_is_rejected(monkeypatch) -> None:
    cookie = session.create_session_cookie("tok")
    real_time = time.time
    monkeypatch.setattr(session.time, "time", lambda: real_time() + 3601)

    assert session.read_session_cookie(cookie) is None


def test_cookie_without_token_is_rejected() -> None:
    payload = json.dumps({"iat": int(time.time())}).encode()

    assert session.read_session_cookie(session._sign(payload)) is None


def test_non_json_payload_is_rejected() -> None:
    assert session.read_session_cookie(session._sign(b"not json")) is None


def test_signing_falls_back_to_the_oauth2_client_secret(monkeypatch) -> None:
    monkeypatch.setattr(settings, "session_secret", "")
    monkeypatch.setattr(settings, "oauth2_client_secret", "client-secret")
    cookie = session.create_session_cookie("tok")

    assert session.read_session_cookie(cookie).token == "tok"
    monkeypatch.setattr(settings, "oauth2_client_secret", "different")
    assert session.read_session_cookie(cookie) is None


def test_pkce_challenge_is_the_s256_of_the_verifier() -> None:
    verifier, challenge = session.generate_pkce()

    digest = hashlib.sha256(verifier.encode()).digest()
    assert challenge == base64.urlsafe_b64encode(digest).rstrip(b"=").decode()
    assert len(verifier) >= 43
    assert session.generate_pkce()[0] != verifier


def test_state_cookie_round_trip() -> None:
    cookie = session.create_state_cookie("state-1", "verifier-1")

    assert session.read_state_cookie(cookie) == ("state-1", "verifier-1")


def test_state_cookie_rejects_forgeries_and_wrong_payloads() -> None:
    assert session.read_state_cookie("garbage") is None
    assert session.read_state_cookie(session.create_session_cookie("tok")) is None
    assert session.read_state_cookie(session._sign(b"nope")) is None
