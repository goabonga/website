# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Analytics service tools — overview, pages, and campaigns stats."""

from team.config import get_settings
from team.services.tool_service import ToolService
from team.services.tools._http import get_service_client


def _get_base_url(context: dict) -> str:
    """Resolve analytics base URL: agent credentials first, then global settings."""
    agent_config = context.get("agent_config", {})
    url = agent_config.get("credentials", {}).get("analytics_base_url", "")
    if url:
        return url
    return get_settings().analytics_base_url


def _get_headers(context: dict) -> dict:
    """Build authorization headers for the analytics service."""
    agent_config = context.get("agent_config", {})
    token = agent_config.get("credentials", {}).get("analytics_token", "")
    if not token:
        token = get_settings().oauth2_client_secret
    return {"Authorization": f"Bearer {token}"}


# --- analytics_overview ---

OVERVIEW_DEFINITION = {
    "name": "analytics_overview",
    "description": "Get overview stats (sessions, visitors, pageviews, events) from analytics.",
    "parameters": {
        "type": "object",
        "properties": {
            "days": {
                "type": "integer",
                "description": "Number of days to look back",
                "default": 30,
            },
        },
        "required": [],
    },
}


@ToolService.register("analytics_overview", OVERVIEW_DEFINITION)
async def analytics_overview(params: dict, context: dict) -> dict:
    """Get overview analytics stats."""
    base_url = _get_base_url(context)
    if not base_url:
        return {"error": "Analytics base URL not configured"}

    tool_service: ToolService = context["tool_service"]
    client, effective_url, should_close = await get_service_client(tool_service, base_url)

    try:
        query: dict = {}
        if params.get("days"):
            query["days"] = params["days"]

        response = await client.get(
            f"{effective_url}/api/v1/stats/overview",
            headers=_get_headers(context),
            params=query,
        )
        if response.status_code == 200:
            return response.json()
        return {"error": f"Analytics API error {response.status_code}: {response.text[:500]}"}
    finally:
        if should_close:
            await client.aclose()


# --- analytics_pages ---

PAGES_DEFINITION = {
    "name": "analytics_pages",
    "description": "Get top pages by pageviews from analytics.",
    "parameters": {
        "type": "object",
        "properties": {
            "days": {
                "type": "integer",
                "description": "Number of days to look back",
                "default": 30,
            },
            "limit": {
                "type": "integer",
                "description": "Max pages to return",
                "default": 20,
            },
        },
        "required": [],
    },
}


@ToolService.register("analytics_pages", PAGES_DEFINITION)
async def analytics_pages(params: dict, context: dict) -> dict:
    """Get top pages by pageviews."""
    base_url = _get_base_url(context)
    if not base_url:
        return {"error": "Analytics base URL not configured"}

    tool_service: ToolService = context["tool_service"]
    client, effective_url, should_close = await get_service_client(tool_service, base_url)

    try:
        query: dict = {}
        if params.get("days"):
            query["days"] = params["days"]
        if params.get("limit"):
            query["limit"] = params["limit"]

        response = await client.get(
            f"{effective_url}/api/v1/stats/pages",
            headers=_get_headers(context),
            params=query,
        )
        if response.status_code == 200:
            return response.json()
        return {"error": f"Analytics API error {response.status_code}: {response.text[:500]}"}
    finally:
        if should_close:
            await client.aclose()


# --- analytics_campaigns ---

CAMPAIGNS_DEFINITION = {
    "name": "analytics_campaigns",
    "description": "List marketing campaigns with click/open counts from analytics.",
    "parameters": {
        "type": "object",
        "properties": {
            "include_inactive": {
                "type": "boolean",
                "description": "Include inactive campaigns",
                "default": False,
            },
            "limit": {
                "type": "integer",
                "description": "Max campaigns to return",
                "default": 20,
            },
        },
        "required": [],
    },
}


@ToolService.register("analytics_campaigns", CAMPAIGNS_DEFINITION)
async def analytics_campaigns(params: dict, context: dict) -> dict:
    """List marketing campaigns with stats."""
    base_url = _get_base_url(context)
    if not base_url:
        return {"error": "Analytics base URL not configured"}

    tool_service: ToolService = context["tool_service"]
    client, effective_url, should_close = await get_service_client(tool_service, base_url)

    try:
        query: dict = {}
        if params.get("include_inactive"):
            query["include_inactive"] = "true"
        if params.get("limit"):
            query["limit"] = params["limit"]

        response = await client.get(
            f"{effective_url}/api/v1/stats/campaigns",
            headers=_get_headers(context),
            params=query,
        )
        if response.status_code == 200:
            return response.json()
        return {"error": f"Analytics API error {response.status_code}: {response.text[:500]}"}
    finally:
        if should_close:
            await client.aclose()
