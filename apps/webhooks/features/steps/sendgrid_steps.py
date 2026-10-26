# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Step definitions for the SendGrid feature (real ECDSA signatures)."""

import base64

from behave import given, when
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from httpx import ASGITransport, AsyncClient
from webhooks.config import settings

TIMESTAMP = "1700000000"


def _public_pem(private_key):
    return (
        private_key.public_key()
        .public_bytes(
            serialization.Encoding.PEM,
            serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        .decode()
    )


def _sign(private_key, body):
    signature = private_key.sign(TIMESTAMP.encode() + body, ec.ECDSA(hashes.SHA256()))
    return base64.b64encode(signature).decode()


def _post_signed(context, path, private_key):
    body = context.text.encode()
    headers = {
        "Content-Type": "application/json",
        "X-Twilio-Email-Event-Webhook-Signature": _sign(private_key, body),
        "X-Twilio-Email-Event-Webhook-Timestamp": TIMESTAMP,
    }

    async def make_request():
        async with AsyncClient(
            transport=ASGITransport(app=context.app), base_url="http://test"
        ) as client:
            return await client.post(path, content=body, headers=headers)

    context.response = context.loop.run_until_complete(make_request())


@given("a SendGrid verification key is configured")
def step_configure_verification_key(context):
    """Generate an ECDSA key pair and configure its public half."""
    context.sendgrid_private_key = ec.generate_private_key(ec.SECP256R1())
    name = "sendgrid_webhook_verification_key"
    context.setting_backup.setdefault(name, getattr(settings, name))
    setattr(settings, name, _public_pem(context.sendgrid_private_key))


@when('I send a SendGrid-signed POST request to "{path}" with body')
def step_send_signed_post(context, path):
    """Send a POST request signed with the configured key."""
    _post_signed(context, path, context.sendgrid_private_key)


@when('I send a SendGrid POST request signed with another key to "{path}" with body')
def step_send_wrongly_signed_post(context, path):
    """Send a POST request signed with an unrelated key."""
    _post_signed(context, path, ec.generate_private_key(ec.SECP256R1()))
