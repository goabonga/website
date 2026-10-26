# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Steps for the share notification feature (mailler faked in-process)."""

import json

import httpx
from apt_server.config import settings
from apt_server.services import mailler
from behave import given, then

REAL_ASYNC_CLIENT = httpx.AsyncClient


def install_fake_mailler(context, backend, failing=False):
    context.mails = []
    context.patch(settings, "email_backend", backend)
    context.patch(settings, "mailler_client_id", "cid")
    context.patch(settings, "mailler_client_secret", "csecret")
    context.patch(settings, "mailler_auth_url", "https://auth.example")
    context.patch(mailler, "_cached_token", "")
    context.patch(mailler, "_token_expires_at", 0)

    def handler(request):
        if request.url.path == "/oauth2/token":
            return httpx.Response(200, json={"access_token": "t", "expires_in": 3600})
        if failing:
            return httpx.Response(503, text="unavailable")
        context.mails.append(json.loads(request.content))
        return httpx.Response(202)

    context.patch(
        mailler.httpx,
        "AsyncClient",
        lambda **kwargs: REAL_ASYNC_CLIENT(
            transport=httpx.MockTransport(handler),
            **{k: v for k, v in kwargs.items() if k != "transport"},
        ),
    )


@given("the mailler service is enabled")
def mailler_enabled(context):
    install_fake_mailler(context, "mailler")


@given("the mailler service is disabled")
def mailler_disabled(context):
    install_fake_mailler(context, "")


@given("the mailler service is enabled but failing")
def mailler_failing(context):
    install_fake_mailler(context, "mailler", failing=True)


@then('the mailler service received a message for "{email}"')
def received_message(context, email):
    assert [m["to_email"] for m in context.mails] == [email], context.mails


@then('the message subject mentions "{text}"')
def subject_mentions(context, text):
    assert text in context.mails[0]["subject"]


@then("the message links to the package page")
def message_links(context):
    assert "/packages/" in context.mails[0]["html_content"]


@then("the mailler service received no message")
def received_nothing(context):
    assert context.mails == []
