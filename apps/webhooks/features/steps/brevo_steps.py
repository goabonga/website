# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Step definitions for the Brevo feature."""

import hashlib
import hmac

from behave import when
from httpx import ASGITransport, AsyncClient
from webhooks.config import settings


@when('I send a Brevo-signed POST request to "{path}" with body')
def step_send_brevo_signed_post(context, path):
    """Send a POST request with a valid Brevo HMAC-SHA256 signature."""
    body = context.text.encode()
    signature = hmac.new(settings.brevo_webhook_secret.encode(), body, hashlib.sha256).hexdigest()

    async def make_request():
        async with AsyncClient(
            transport=ASGITransport(app=context.app), base_url="http://test"
        ) as client:
            return await client.post(
                path,
                content=body,
                headers={
                    "Content-Type": "application/json",
                    "X-Sib-Webhook-Signature": signature,
                },
            )

    context.response = context.loop.run_until_complete(make_request())
