# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""http_request tool — make HTTP requests to external APIs."""

from team.services.tool_service import ToolService

DEFINITION = {
    "name": "http_request",
    "description": "Make an HTTP request to an external API.",
    "parameters": {
        "type": "object",
        "properties": {
            "url": {"type": "string", "description": "Request URL"},
            "method": {"type": "string", "description": "HTTP method", "default": "GET"},
            "headers": {"type": "object", "description": "Request headers"},
            "body": {"type": "object", "description": "Request body (JSON)"},
        },
        "required": ["url"],
    },
}

MAX_BODY_LENGTH = 4000


@ToolService.register("http_request", DEFINITION)
async def http_request(params: dict, context: dict) -> dict:
    """Make an HTTP request and return the response."""
    tool_service: ToolService = context["tool_service"]
    client = await tool_service.get_client()

    method = params.get("method", "GET").upper()
    url = params["url"]
    headers = params.get("headers", {})
    body = params.get("body")

    response = await client.request(method, url, headers=headers, json=body)
    return {
        "status_code": response.status_code,
        "body": response.text[:MAX_BODY_LENGTH],
    }
