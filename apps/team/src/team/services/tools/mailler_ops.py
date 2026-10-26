# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Mailler service tools — send emails, stats, templates, and campaigns."""

from team.config import get_settings
from team.services.tool_service import ToolService
from team.services.tools._http import get_service_client


def _get_base_url(context: dict) -> str:
    """Resolve mailler base URL: agent credentials first, then global settings."""
    agent_config = context.get("agent_config", {})
    url = agent_config.get("credentials", {}).get("mailler_base_url", "")
    if url:
        return url
    return get_settings().mailler_base_url


def _get_headers(context: dict) -> dict:
    """Build authorization headers for the mailler service."""
    agent_config = context.get("agent_config", {})
    token = agent_config.get("credentials", {}).get("mailler_token", "")
    if not token:
        token = get_settings().oauth2_client_secret
    return {"Authorization": f"Bearer {token}"}


# --- mailler_send_email ---

SEND_EMAIL_DEFINITION = {
    "name": "mailler_send_email",
    "description": "Send an email immediately via the mailler service.",
    "parameters": {
        "type": "object",
        "properties": {
            "to_email": {"type": "string", "description": "Recipient email address"},
            "subject": {"type": "string", "description": "Email subject line"},
            "html_content": {"type": "string", "description": "HTML email body"},
            "text_content": {"type": "string", "description": "Plain-text fallback body"},
            "from_email": {"type": "string", "description": "Sender email address (optional)"},
            "provider": {
                "type": "string",
                "description": "Email provider (brevo, sendgrid, ses)",
            },
        },
        "required": ["to_email", "subject", "html_content"],
    },
}


@ToolService.register("mailler_send_email", SEND_EMAIL_DEFINITION)
async def mailler_send_email(params: dict, context: dict) -> dict:
    """Send an email immediately."""
    base_url = _get_base_url(context)
    if not base_url:
        return {"error": "Mailler base URL not configured"}

    tool_service: ToolService = context["tool_service"]
    client, effective_url, should_close = await get_service_client(tool_service, base_url)

    try:
        payload: dict = {
            "to_email": params["to_email"],
            "subject": params["subject"],
            "html_content": params["html_content"],
        }
        if params.get("text_content"):
            payload["text_content"] = params["text_content"]
        if params.get("from_email"):
            payload["from_email"] = params["from_email"]
        if params.get("provider"):
            payload["provider"] = params["provider"]

        response = await client.post(
            f"{effective_url}/api/v1/send",
            headers=_get_headers(context),
            json=payload,
        )
        if response.status_code in (200, 201):
            return response.json()
        return {"error": f"Mailler API error {response.status_code}: {response.text[:500]}"}
    finally:
        if should_close:
            await client.aclose()


# --- mailler_get_stats ---

GET_STATS_DEFINITION = {
    "name": "mailler_get_stats",
    "description": "Get email delivery statistics from the mailler service.",
    "parameters": {
        "type": "object",
        "properties": {
            "start_date": {"type": "string", "description": "Start date (YYYY-MM-DD)"},
            "end_date": {"type": "string", "description": "End date (YYYY-MM-DD)"},
            "provider": {
                "type": "string",
                "description": "Filter by provider (brevo, sendgrid, ses)",
            },
        },
        "required": [],
    },
}


@ToolService.register("mailler_get_stats", GET_STATS_DEFINITION)
async def mailler_get_stats(params: dict, context: dict) -> dict:
    """Get email delivery statistics."""
    base_url = _get_base_url(context)
    if not base_url:
        return {"error": "Mailler base URL not configured"}

    tool_service: ToolService = context["tool_service"]
    client, effective_url, should_close = await get_service_client(tool_service, base_url)

    try:
        query: dict = {}
        if params.get("start_date"):
            query["start_date"] = params["start_date"]
        if params.get("end_date"):
            query["end_date"] = params["end_date"]
        if params.get("provider"):
            query["provider"] = params["provider"]

        response = await client.get(
            f"{effective_url}/api/v1/stats",
            headers=_get_headers(context),
            params=query,
        )
        if response.status_code == 200:
            return response.json()
        return {"error": f"Mailler API error {response.status_code}: {response.text[:500]}"}
    finally:
        if should_close:
            await client.aclose()


# --- mailler_list_templates ---

LIST_TEMPLATES_DEFINITION = {
    "name": "mailler_list_templates",
    "description": "List email templates from the mailler service.",
    "parameters": {
        "type": "object",
        "properties": {
            "page": {"type": "integer", "description": "Page number", "default": 1},
            "page_size": {"type": "integer", "description": "Results per page", "default": 20},
            "status": {"type": "string", "description": "Filter by status (active, draft)"},
            "search": {"type": "string", "description": "Search by template name"},
        },
        "required": [],
    },
}


@ToolService.register("mailler_list_templates", LIST_TEMPLATES_DEFINITION)
async def mailler_list_templates(params: dict, context: dict) -> dict:
    """List email templates."""
    base_url = _get_base_url(context)
    if not base_url:
        return {"error": "Mailler base URL not configured"}

    tool_service: ToolService = context["tool_service"]
    client, effective_url, should_close = await get_service_client(tool_service, base_url)

    try:
        query: dict = {}
        if params.get("page"):
            query["page"] = params["page"]
        if params.get("page_size"):
            query["page_size"] = params["page_size"]
        if params.get("status"):
            query["status"] = params["status"]
        if params.get("search"):
            query["search"] = params["search"]

        response = await client.get(
            f"{effective_url}/api/v1/templates",
            headers=_get_headers(context),
            params=query,
        )
        if response.status_code == 200:
            return response.json()
        return {"error": f"Mailler API error {response.status_code}: {response.text[:500]}"}
    finally:
        if should_close:
            await client.aclose()


# --- mailler_start_campaign ---

START_CAMPAIGN_DEFINITION = {
    "name": "mailler_start_campaign",
    "description": "Start sending a campaign via the mailler service.",
    "parameters": {
        "type": "object",
        "properties": {
            "campaign_id": {"type": "string", "description": "Campaign ID to start sending"},
        },
        "required": ["campaign_id"],
    },
}


@ToolService.register("mailler_start_campaign", START_CAMPAIGN_DEFINITION)
async def mailler_start_campaign(params: dict, context: dict) -> dict:
    """Start sending a campaign."""
    base_url = _get_base_url(context)
    if not base_url:
        return {"error": "Mailler base URL not configured"}

    tool_service: ToolService = context["tool_service"]
    client, effective_url, should_close = await get_service_client(tool_service, base_url)

    try:
        response = await client.post(
            f"{effective_url}/api/v1/campaigns/{params['campaign_id']}/send",
            headers=_get_headers(context),
        )
        if response.status_code in (200, 201):
            return response.json()
        return {"error": f"Mailler API error {response.status_code}: {response.text[:500]}"}
    finally:
        if should_close:
            await client.aclose()
