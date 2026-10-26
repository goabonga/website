# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Steps for the email delivery feature.

The templates are the real shipped files. The mailler service is replaced by an httpx
mock transport and the OAuth2 server by a fake token cache that records the requests.
"""

import json
import subprocess
import sys
from unittest.mock import patch

import httpx
from behave import given, then, when

from knowledge import email_templates
from knowledge.services.mailler import MaillerClient, MaillerError


def _patch(context, target, value, attribute=False):
    patcher = patch.object(*target, value) if attribute else patch(target, value)
    patcher.start()
    context.add_cleanup(patcher.stop)


# --- shipped templates ----------------------------------------------------


@given('the shipped "{slug}" email template')
def step_template(context, slug):
    context.slug = slug
    context.source = (email_templates.TEMPLATES_DIR / f"{slug}.mjml").read_text()
    context.description = json.loads((email_templates.TEMPLATES_DIR / f"{slug}.json").read_text())


@then("the template should have a source and a description for mailler")
def step_source_and_description(context):
    assert context.source.lstrip().startswith("<mjml>")
    assert context.description["subject_template"]
    assert set(context.description) <= {"name", "description", "subject_template", "plain_text"}


@then('the template should use "{first}", "{second}" and "{third}"')
def step_uses(context, first, second, third):
    text = context.source + context.description["subject_template"]
    for name in (first, second, third):
        assert "{{ " + name + " }}" in text, name


@when("I ask for the template directory")
def step_directory(context):
    context.output = subprocess.run(
        [sys.executable, "-m", "knowledge.email_templates"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()


@then("it should contain the {count:d} templates")
def step_directory_content(context, count):
    assert context.output == str(email_templates.TEMPLATES_DIR)
    assert len(email_templates.template_slugs()) == count


# --- the mailler service --------------------------------------------------


class _Tokens:
    """Stands in for the OAuth2 server: records the token requests."""

    def __init__(self, requests):
        self.requests = requests

    def get(self, credentials, scope):
        self.requests.append(("client_credentials", scope))
        return "token-1"

    def clear(self):
        pass


def _client(context, handler, configured=True):
    client = MaillerClient()
    client.url = "http://mailler.test" if configured else ""
    client.socket_path = ""
    context.token_requests = []
    context.mailler_requests = []
    client._tokens = _Tokens(context.token_requests)

    def recording(request):
        context.mailler_requests.append(request)
        return handler(request)

    real_client = httpx.Client
    client._http_client = lambda: real_client(transport=httpx.MockTransport(recording))
    context.mailler = client
    context.result = None
    context.error = None


def _accepting(extra=None):
    body = {"id": "mail-1", "status": "queued", "message": "Email queued", "task_id": "t1"}
    body.update(extra or {})
    return lambda request: httpx.Response(200, json=body)


@given("a mailler service that accepts emails")
def step_accepts(context):
    _client(context, _accepting())


@given('a mailler service that reports the missing variable "{name}"')
def step_missing(context, name):
    _client(context, _accepting({"missing_variables": [name]}))


@given('a mailler service that answers {status:d} "{detail}"')
def step_answers(context, status, detail):
    _client(context, lambda request: httpx.Response(status, json={"detail": detail}))


@given("a mailler service that is down")
def step_down(context):
    def handler(request):
        raise httpx.ConnectError("connection refused")

    _client(context, handler)


@given("no mailler service is configured")
def step_unconfigured(context):
    _client(context, lambda request: httpx.Response(500), configured=False)


VARIABLES = {"workspace_name": "Acme", "year": 2026}


@when('the application sends the "{slug}" template to "{to}" with the key "{key}"')
def step_send_with_key(context, slug, to, key):
    context.result = context.mailler.send_template(slug, to, VARIABLES, idempotency_key=key)


@when('the application tries to send the "{slug}" template to "{to}"')
def step_try_send(context, slug, to):
    try:
        context.mailler.send_template(slug, to, VARIABLES)
    except MaillerError as error:
        context.error = error


@then("the email should be accepted")
def step_accepted(context):
    assert context.result is not None and context.result.id == "mail-1"


@then('the missing variables should be "{names}"')
def step_missing_variables(context, names):
    assert context.result.missing_variables == names.split(",")


@then('mailler should have received a "{grant}" token request for the scope "{scope}"')
def step_token_request(context, grant, scope):
    assert (grant, scope) in context.token_requests, context.token_requests


def _body(context):
    return json.loads(context.mailler_requests[-1].content)


@then(
    'mailler should have received the template "{slug}" for "{to}" with the variable "{name}" set to "{value}"'
)
def step_received(context, slug, to, name, value):
    request = context.mailler_requests[-1]
    assert str(request.url) == "http://mailler.test/api/v1/send"
    assert request.headers["authorization"] == "Bearer token-1"
    body = _body(context)
    assert body["template_slug"] == slug
    assert body["to_email"] == to
    assert body["variables"][name] == value


@then('the request should carry the idempotency key "{key}"')
def step_key(context, key):
    assert context.mailler_requests[-1].headers["idempotency-key"] == key


@then("the request should not name a sender, a provider or a subject")
def step_no_sender(context):
    assert not {"from_email", "from_name", "reply_to", "provider", "subject"} & set(_body(context))


@then("the email should be refused with {status:d}")
def step_refused(context, status):
    assert context.error is not None and context.error.status_code == status, context.error


@then("the email should be refused without a status")
def step_refused_without_status(context):
    assert context.error is not None and context.error.status_code is None, context.error


@then("sending again {verdict}")
def step_verdict(context, verdict):
    assert context.error.retryable is (verdict == "can work"), context.error
