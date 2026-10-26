# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for knowledge/services/mailler.py: the client of the mailler service."""

import json
from unittest.mock import MagicMock, patch

import httpx
import pytest

from knowledge.services import mailler
from knowledge.services.mailler import MaillerClient, MaillerError, get_mailler_client
from knowledge.services.service_auth import ServiceAuthError


def _settings(**overrides):
    settings = MagicMock()
    settings.mailler_url = "http://mailler.test/"
    settings.mailler_socket_path = ""
    settings.service_timeout = 7.0
    for key, value in overrides.items():
        setattr(settings, key, value)
    return settings


def _client(**overrides) -> MaillerClient:
    with patch.object(mailler, "get_settings", return_value=_settings(**overrides)):
        client = MaillerClient()
    client._tokens = MagicMock()
    client._tokens.get.return_value = "tok"
    return client


class _Recorder:
    """Stands in for the HTTP client: answers with the given responses, records the requests."""

    def __init__(self, *responses):
        self.responses = list(responses)
        self.requests = []

    def __call__(self):
        return self

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def post(self, url, json=None, headers=None):
        self.requests.append((url, json, headers))
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


def _answer(status=200, body=None, text=""):
    response = MagicMock(spec=httpx.Response)
    response.status_code = status
    response.text = text
    if body is None:
        response.json.side_effect = ValueError("no json")
    else:
        response.json.return_value = body
    return response


OK = {"id": "mail-1", "status": "queued", "message": "Email queued", "task_id": "t1"}


def _send(client, recorder, **kwargs):
    client._http_client = recorder
    return client.send_template(
        "workspace_invitation", "ann@example.test", {"workspace_name": "Acme"}, **kwargs
    )


class TestConfiguration:
    def test_url_without_trailing_slash(self):
        client = _client()
        assert client.is_configured is True
        assert client.base_url == "http://mailler.test"

    def test_socket_uses_a_placeholder_host(self):
        client = _client(mailler_url="", mailler_socket_path="/run/mailler/mailler.sock")
        assert client.is_configured is True
        assert client.base_url == "http://localhost"

    def test_nothing_configured(self):
        client = _client(mailler_url="", mailler_socket_path="")
        assert client.is_configured is False
        with pytest.raises(MaillerError, match="not configured") as error:
            client.send_template("welcome", "ann@example.test", {})
        assert error.value.retryable is False

    def test_timeout_comes_from_the_settings(self):
        assert _client().timeout == 7.0

    def test_http_client_over_a_socket(self):
        client = _client(mailler_url="", mailler_socket_path="/run/mailler/mailler.sock")
        with patch.object(mailler.httpx, "HTTPTransport") as transport:
            http = client._http_client()
        transport.assert_called_once_with(uds="/run/mailler/mailler.sock")
        http.close()

    def test_http_client_over_http(self):
        http = _client()._http_client()
        assert http.timeout.read == 7.0
        http.close()


class TestSendTemplate:
    def test_sends_the_slug_and_the_variables_with_a_token(self):
        client = _client()
        recorder = _Recorder(_answer(body=OK))

        result = _send(client, recorder, to_name="Ann", metadata={"invitation": 42})

        url, body, headers = recorder.requests[0]
        assert url == "http://mailler.test/api/v1/send"
        assert body == {
            "to_email": "ann@example.test",
            "template_slug": "workspace_invitation",
            "variables": {"workspace_name": "Acme"},
            "to_name": "Ann",
            "metadata": {"invitation": 42},
        }
        assert headers == {"Authorization": "Bearer tok"}
        assert result.id == "mail-1"
        assert result.status == "queued"
        assert result.task_id == "t1"
        assert result.missing_variables == []

    def test_the_token_is_requested_for_the_send_scope_of_the_mailler_client(self):
        client = _client()
        with patch.object(mailler, "credentials_for", return_value="creds") as credentials:
            _send(client, _Recorder(_answer(body=OK)))
        credentials.assert_called_once_with("mailler")
        client._tokens.get.assert_called_once_with("creds", "mailler:send")

    def test_no_sender_is_sent_because_mailler_decides_it(self):
        recorder = _Recorder(_answer(body=OK))
        _send(_client(), recorder)
        body = recorder.requests[0][1]
        assert not {"from_email", "from_name", "reply_to", "provider", "subject"} & set(body)

    def test_idempotency_key_is_sent_as_a_header(self):
        recorder = _Recorder(_answer(body=OK))
        _send(_client(), recorder, idempotency_key="task-1")
        assert recorder.requests[0][2]["Idempotency-Key"] == "task-1"

    def test_missing_variables_are_reported_and_logged(self, caplog):
        recorder = _Recorder(_answer(body={**OK, "missing_variables": ["role"]}))
        with caplog.at_level("WARNING"):
            result = _send(_client(), recorder)
        assert result.missing_variables == ["role"]
        assert "role" in caplog.text

    def test_expired_token_is_renewed_once(self):
        client = _client()
        recorder = _Recorder(_answer(status=401, body={"detail": "expired"}), _answer(body=OK))
        result = _send(client, recorder)
        assert result.id == "mail-1"
        assert len(recorder.requests) == 2

    def test_token_refused_twice_is_an_error(self):
        client = _client()
        recorder = _Recorder(_answer(status=401), _answer(status=401))
        with pytest.raises(MaillerError) as error:
            _send(client, recorder)
        assert error.value.status_code == 401
        assert error.value.retryable is False


class TestRefusals:
    @pytest.mark.parametrize(
        ("status", "retryable"),
        [
            (403, False),  # client not registered, deactivated or sender not allowed
            (404, False),  # unknown template
            (422, False),  # not active, not renderable, invalid body
            (400, False),
            (429, True),  # rate limit or daily quota reached
            (500, True),
            (502, True),
            (503, True),
        ],
    )
    def test_status_decides_whether_to_retry(self, status, retryable):
        recorder = _Recorder(_answer(status=status, body={"detail": "because"}))
        with pytest.raises(MaillerError, match="because") as error:
            _send(_client(), recorder)
        assert error.value.status_code == status
        assert error.value.retryable is retryable

    def test_detail_that_is_not_text(self):
        recorder = _Recorder(_answer(status=422, body={"detail": [{"msg": "bad"}]}))
        with pytest.raises(MaillerError, match="bad"):
            _send(_client(), recorder)

    def test_answer_that_is_not_json(self):
        recorder = _Recorder(_answer(status=502, text="Bad gateway"))
        with pytest.raises(MaillerError, match="Bad gateway") as error:
            _send(_client(), recorder)
        assert error.value.retryable is True

    def test_body_without_detail(self):
        recorder = _Recorder(_answer(status=500, body={"error": "x"}, text="oops"))
        with pytest.raises(MaillerError, match="oops"):
            _send(_client(), recorder)

    def test_network_error_can_pass(self):
        recorder = _Recorder(httpx.ConnectError("down"))
        with pytest.raises(MaillerError, match="request failed") as error:
            _send(_client(), recorder)
        assert error.value.retryable is True

    def test_unexpected_success_body(self):
        recorder = _Recorder(_answer(body={"nope": 1}))
        with pytest.raises(MaillerError, match="unexpected") as error:
            _send(_client(), recorder)
        assert error.value.retryable is False

    @pytest.mark.parametrize("retryable", [True, False])
    def test_token_failure_keeps_its_retryable_flag(self, retryable):
        client = _client()
        client._tokens.get.side_effect = ServiceAuthError("no token", retryable=retryable)
        with pytest.raises(MaillerError, match="no token") as error:
            _send(client, _Recorder())
        assert error.value.retryable is retryable


class TestRealTransport:
    """The request really goes through httpx: URL, body and headers on the wire."""

    def test_request_on_the_wire(self):
        seen = {}

        def handler(request: httpx.Request) -> httpx.Response:
            seen["request"] = request
            return httpx.Response(200, json=OK)

        client = _client()
        real_client = httpx.Client
        with patch.object(
            mailler.httpx,
            "Client",
            lambda **kwargs: real_client(transport=httpx.MockTransport(handler)),
        ):
            result = client.send_template(
                "workspace_deleted", "ann@example.test", {"year": 2026}, idempotency_key="k"
            )

        request = seen["request"]
        assert str(request.url) == "http://mailler.test/api/v1/send"
        assert request.headers["authorization"] == "Bearer tok"
        assert request.headers["idempotency-key"] == "k"
        assert json.loads(request.content)["variables"] == {"year": 2026}
        assert result.id == "mail-1"


def test_get_mailler_client_is_a_singleton():
    mailler._client = None
    with patch.object(mailler, "get_settings", return_value=_settings()):
        first = get_mailler_client()
        assert get_mailler_client() is first
    mailler._client = None
