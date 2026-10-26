# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""service_call tool — call internal microservices."""

from team.config import get_settings
from team.services.tool_service import ToolService
from team.services.tools._http import get_service_client

MAX_BODY_LENGTH = 4000

DEFINITION = {
    "name": "service_call",
    "description": "Call an internal microservice (e.g., mailer, analytics).",
    "parameters": {
        "type": "object",
        "properties": {
            "service": {
                "type": "string",
                "description": "Service name (e.g., 'mailer', 'analytics')",
            },
            "endpoint": {"type": "string", "description": "API endpoint path"},
            "method": {"type": "string", "description": "HTTP method", "default": "GET"},
            "body": {"type": "object", "description": "Request body (JSON)"},
            "headers": {"type": "object", "description": "Extra request headers"},
        },
        "required": ["service", "endpoint"],
    },
}


def _get_services_base_url(context: dict) -> str:
    """Resolve services base URL: agent credentials first, then global settings."""
    agent_config = context.get("agent_config", {})
    url = agent_config.get("credentials", {}).get("services_base_url", "")
    if url:
        return url
    return get_settings().services_base_url


@ToolService.register("service_call", DEFINITION)
async def service_call(params: dict, context: dict) -> dict:
    """Call an internal microservice."""
    base_url = _get_services_base_url(context)
    if not base_url:
        return {"error": "Services base URL not configured"}

    tool_service: ToolService = context["tool_service"]
    client, effective_url, should_close = await get_service_client(tool_service, base_url)

    try:
        service = params["service"]
        endpoint = params["endpoint"].lstrip("/")
        method = params.get("method", "GET").upper()
        url = f"{effective_url}/{service}/{endpoint}"

        headers = params.get("headers", {})
        body = params.get("body")

        # Pass agent-level service API key if configured
        agent_config = context.get("agent_config", {})
        api_key = agent_config.get("credentials", {}).get("services_api_key", "")
        if api_key:
            headers.setdefault("Authorization", f"Bearer {api_key}")

        response = await client.request(method, url, headers=headers, json=body)
        return {
            "status_code": response.status_code,
            "body": response.text[:MAX_BODY_LENGTH],
        }
    finally:
        if should_close:
            await client.aclose()
