# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""MJML share notification and its delivery."""

import pytest
from apt_server.config import settings
from apt_server.services import email, mailler

VARIABLES = {
    "app_name": "Test Registry",
    "sharer": "alice@example.com",
    "role": "write",
    "package_name": "demo-tool",
    "package_version": "1.2.3",
    "package_arch": "amd64",
    "package_component": "private",
    "package_url": "https://apt.example.com/packages/abc",
}


@pytest.fixture(autouse=True)
def reset_cache(monkeypatch):
    monkeypatch.setattr(email, "_compiled_cache", {})


def test_template_is_compiled_to_html_with_variables() -> None:
    html = email.render("package_shared", **VARIABLES)

    assert html.lstrip().lower().startswith("<!doctype html")
    for value in VARIABLES.values():
        assert value in html
    assert "%sharer%" not in html and "{{" not in html


def test_compiled_templates_are_cached() -> None:
    first = email._compile_mjml("package_shared")

    assert email._compile_mjml("package_shared") is first
    assert "package_shared" in email._compiled_cache


def test_unknown_template_is_reported() -> None:
    with pytest.raises(FileNotFoundError, match="email template not found"):
        email.render("does_not_exist")


async def test_share_notification_is_sent_through_mailler(monkeypatch) -> None:
    sent: list[dict] = []

    async def fake_send(**kwargs) -> None:
        sent.append(kwargs)

    monkeypatch.setattr(settings, "email_backend", "Mailler")
    monkeypatch.setattr(mailler, "send_email", fake_send)

    await email.send_package_shared(
        to_email="bob@example.com",
        to_name="bob",
        sharer="alice@example.com",
        role="read",
        package_name="demo-tool",
        package_version="1.2.3",
        package_arch="amd64",
        package_component="main",
        package_url="https://apt.example.com/packages/abc",
    )

    (message,) = sent
    assert message["to_email"] == "bob@example.com"
    assert message["subject"] == "alice@example.com shared demo-tool 1.2.3 with you"
    assert "demo-tool" in message["html_content"]


async def test_share_notification_is_skipped_when_email_is_disabled(monkeypatch) -> None:
    async def fail(**kwargs) -> None:
        raise AssertionError("must not send")

    monkeypatch.setattr(settings, "email_backend", "")
    monkeypatch.setattr(mailler, "send_email", fail)

    await email.send_package_shared(
        to_email="bob@example.com",
        to_name="bob",
        sharer="alice",
        role="read",
        package_name="p",
        package_version="1",
        package_arch="all",
        package_component="main",
        package_url="https://x",
    )
