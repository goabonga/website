# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for custom_domain/webhook_signature.py and the SDK helpers built on it."""

import hashlib
import hmac
import json

import pytest
from custom_domain.client import (
    WebhookEvent,
    WebhookSignatureError,
    construct_event,
    verify_webhook_signature,
)
from custom_domain.webhook_signature import (
    SignatureError,
    sign,
    signature_header,
    verify_signature,
)

SECRET = "s" * 32
BODY = b'{"event":"domain.active"}'


class TestSigning:
    """The signature format."""

    def test_signature_is_an_hmac_sha256_of_timestamp_dot_body(self):
        expected = hmac.new(SECRET.encode(), b"1700000000." + BODY, hashlib.sha256).hexdigest()
        assert sign(SECRET, BODY, 1700000000) == expected

    def test_header_format(self):
        header = signature_header(SECRET, BODY, 1700000000)
        assert header == f"t=1700000000,v1={sign(SECRET, BODY, 1700000000)}"

    def test_header_defaults_to_the_current_time(self):
        import time

        stamp = int(signature_header(SECRET, BODY).split(",")[0][2:])
        assert abs(stamp - time.time()) < 5


class TestVerification:
    """Checking a delivery."""

    def test_valid_signature(self):
        header = signature_header(SECRET, BODY, 1000)
        assert verify_signature(SECRET, BODY, header, 300, now=1100) == 1000

    @pytest.mark.parametrize(
        ("mutate", "message"),
        [
            (lambda h, b: (h, b + b" "), "does not match"),
            (lambda h, b: (h.replace("v1=", "v1=0"), b), "does not match"),
            (lambda h, b: (None, b), "Missing"),
            (lambda h, b: ("", b), "Missing"),
            (lambda h, b: ("v1=abc", b), "Malformed"),
            (lambda h, b: ("t=1000", b), "Malformed"),
            (lambda h, b: ("t=soon,v1=abc", b), "Malformed"),
            (lambda h, b: ("garbage", b), "Malformed"),
        ],
    )
    def test_rejected(self, mutate, message):
        header, body = mutate(signature_header(SECRET, BODY, 1000), BODY)
        with pytest.raises(SignatureError, match=message):
            verify_signature(SECRET, body, header, 300, now=1100)

    def test_wrong_secret(self):
        header = signature_header("other-" + SECRET, BODY, 1000)
        with pytest.raises(SignatureError, match="does not match"):
            verify_signature(SECRET, BODY, header, 300, now=1000)

    def test_replay_is_refused(self):
        header = signature_header(SECRET, BODY, 1000)
        with pytest.raises(SignatureError, match="tolerance"):
            verify_signature(SECRET, BODY, header, 300, now=1301)
        with pytest.raises(SignatureError, match="tolerance"):
            verify_signature(SECRET, BODY, header, 300, now=699)
        assert verify_signature(SECRET, BODY, header, 300, now=1300) == 1000

    def test_tolerance_can_be_disabled(self):
        header = signature_header(SECRET, BODY, 1000)
        assert verify_signature(SECRET, BODY, header, None, now=10**10) == 1000

    def test_a_secret_can_be_rotated(self):
        """Several v1 values are accepted: the old and the new secret during a rotation."""
        old = sign("old-" + SECRET, BODY, 1000)
        new = sign(SECRET, BODY, 1000)
        header = f"t=1000,v1={old},v1={new}"
        assert verify_signature(SECRET, BODY, header, None) == 1000


class TestSdkHelpers:
    """custom_domain.client.webhooks."""

    @staticmethod
    def delivery(**overrides):
        document = {
            "id": "delivery-1",
            "event": "domain.active",
            "created_at": "2026-01-01T12:00:00+00:00",
            "domain": {"id": "d1", "domain": "shop.example.com", "status": "active"},
            "data": {"status": "active"},
        }
        document.update(overrides)
        return json.dumps(document).encode()

    def test_construct_event(self):
        body = self.delivery()
        event = construct_event(body, signature_header(SECRET, body), SECRET)
        assert isinstance(event, WebhookEvent)
        assert event.id == "delivery-1"
        assert event.event == "domain.active"
        assert event.status == "active"
        assert event.domain["domain"] == "shop.example.com"
        assert event.data == {"status": "active"}
        assert event.created_at.year == 2026

    def test_bad_signature_raises_the_sdk_error(self):
        body = self.delivery()
        with pytest.raises(WebhookSignatureError, match="does not match"):
            construct_event(body, signature_header("x" * 32, body), SECRET)

    def test_error_is_a_custom_domain_error(self):
        from custom_domain.client import CustomDomainError

        assert issubclass(WebhookSignatureError, CustomDomainError)

    @pytest.mark.parametrize("body", [b"not json", b"[]", b'{"id": "x"}', b"null"])
    def test_malformed_body_is_refused_after_the_signature_check(self, body):
        with pytest.raises(WebhookSignatureError, match="Malformed webhook body"):
            construct_event(body, signature_header(SECRET, body), SECRET)

    def test_verify_returns_the_timestamp(self):
        header = signature_header(SECRET, BODY)
        assert verify_webhook_signature(BODY, header, SECRET) == int(header[2:].split(",")[0])

    def test_event_without_creation_time(self):
        body = json.dumps({"id": "i", "event": "e", "domain": {}}).encode()
        event = construct_event(body, signature_header(SECRET, body), SECRET)
        assert event.created_at is None
        assert event.status is None
        assert event.data == {}

    def test_the_service_and_the_sdk_agree(self):
        """What the delivery task signs is what the SDK verifies."""
        from custom_domain.tasks.webhooks import build_body

        domain = _domain()
        body = build_body(
            domain, "domain.failed", {"code": "X"}, "d-1", "2026-01-01T00:00:00+00:00"
        )
        event = construct_event(body, signature_header(SECRET, body), SECRET)
        assert event.event == "domain.failed"
        assert event.data == {"code": "X"}
        assert event.domain["id"] == str(domain.id)


def _domain():
    from unittest.mock import MagicMock
    from uuid import uuid4

    from custom_domain.models.enums import DomainStatus

    domain = MagicMock()
    domain.id = uuid4()
    domain.domain = "shop.example.com"
    domain.status = DomainStatus.FAILED
    domain.client_id = "tenant-a"
    domain.owner_id = "org_1"
    domain.owner_type = "organization"
    domain.metadata_ = None
    domain.error_message = "boom"
    return domain
