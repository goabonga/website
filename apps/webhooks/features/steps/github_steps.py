# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Step definitions for the GitHub feature."""

import hashlib
import hmac

from behave import when
from httpx import ASGITransport, AsyncClient
from webhooks.config import settings


@when('I send a GitHub-signed POST request to "{path}" with body')
def step_send_github_signed_post(context, path):
    """Send a POST request with a valid GitHub HMAC-SHA256 signature."""
    body = context.text.encode()
    digest = hmac.new(settings.github_webhook_secret.encode(), body, hashlib.sha256).hexdigest()

    async def make_request():
        async with AsyncClient(
            transport=ASGITransport(app=context.app), base_url="http://test"
        ) as client:
            return await client.post(
                path,
                content=body,
                headers={
                    "Content-Type": "application/json",
                    "X-Hub-Signature-256": f"sha256={digest}",
                },
            )

    context.response = context.loop.run_until_complete(make_request())
