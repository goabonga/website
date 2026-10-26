# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Auth service tools — list users, clients, and roles via the admin API."""

from team.config import get_settings
from team.services.tool_service import ToolService
from team.services.tools._http import get_service_client


def _get_base_url(context: dict) -> str:
    """Resolve auth base URL: agent credentials first, then global settings."""
    agent_config = context.get("agent_config", {})
    url = agent_config.get("credentials", {}).get("auth_base_url", "")
    if url:
        return url
    return get_settings().auth_base_url


def _get_headers(context: dict) -> dict:
    """Build authorization headers for the auth admin API."""
    agent_config = context.get("agent_config", {})
    token = agent_config.get("credentials", {}).get("auth_token", "")
    if not token:
        token = get_settings().oauth2_client_secret
    return {"Authorization": f"Bearer {token}"}


# --- auth_list_users ---

LIST_USERS_DEFINITION = {
    "name": "auth_list_users",
    "description": "List users via the auth admin API.",
    "parameters": {
        "type": "object",
        "properties": {
            "search": {"type": "string", "description": "Search by email or username"},
            "limit": {"type": "integer", "description": "Max results", "default": 50},
            "offset": {"type": "integer", "description": "Pagination offset", "default": 0},
            "is_active": {"type": "boolean", "description": "Filter by active status"},
        },
        "required": [],
    },
}


@ToolService.register("auth_list_users", LIST_USERS_DEFINITION)
async def auth_list_users(params: dict, context: dict) -> dict:
    """List users from the auth service."""
    base_url = _get_base_url(context)
    if not base_url:
        return {"error": "Auth base URL not configured"}

    tool_service: ToolService = context["tool_service"]
    client, effective_url, should_close = await get_service_client(tool_service, base_url)

    try:
        query: dict = {}
        if params.get("search"):
            query["search"] = params["search"]
        if params.get("limit"):
            query["limit"] = params["limit"]
        if params.get("offset"):
            query["offset"] = params["offset"]
        if "is_active" in params:
            query["is_active"] = str(params["is_active"]).lower()

        response = await client.get(
            f"{effective_url}/admin/api/users",
            headers=_get_headers(context),
            params=query,
        )
        if response.status_code == 200:
            return response.json()
        return {"error": f"Auth API error {response.status_code}: {response.text[:500]}"}
    finally:
        if should_close:
            await client.aclose()


# --- auth_list_clients ---

LIST_CLIENTS_DEFINITION = {
    "name": "auth_list_clients",
    "description": "List OAuth2 clients via the auth admin API.",
    "parameters": {
        "type": "object",
        "properties": {
            "search": {"type": "string", "description": "Search by client name or ID"},
            "limit": {"type": "integer", "description": "Max results", "default": 50},
            "offset": {"type": "integer", "description": "Pagination offset", "default": 0},
        },
        "required": [],
    },
}


@ToolService.register("auth_list_clients", LIST_CLIENTS_DEFINITION)
async def auth_list_clients(params: dict, context: dict) -> dict:
    """List OAuth2 clients from the auth service."""
    base_url = _get_base_url(context)
    if not base_url:
        return {"error": "Auth base URL not configured"}

    tool_service: ToolService = context["tool_service"]
    client, effective_url, should_close = await get_service_client(tool_service, base_url)

    try:
        query: dict = {}
        if params.get("search"):
            query["search"] = params["search"]
        if params.get("limit"):
            query["limit"] = params["limit"]
        if params.get("offset"):
            query["offset"] = params["offset"]

        response = await client.get(
            f"{effective_url}/admin/api/clients",
            headers=_get_headers(context),
            params=query,
        )
        if response.status_code == 200:
            return response.json()
        return {"error": f"Auth API error {response.status_code}: {response.text[:500]}"}
    finally:
        if should_close:
            await client.aclose()


# --- auth_list_roles ---

LIST_ROLES_DEFINITION = {
    "name": "auth_list_roles",
    "description": "List roles and their scopes via the auth admin API.",
    "parameters": {
        "type": "object",
        "properties": {
            "search": {"type": "string", "description": "Search by role name"},
            "limit": {"type": "integer", "description": "Max results", "default": 50},
            "offset": {"type": "integer", "description": "Pagination offset", "default": 0},
        },
        "required": [],
    },
}


@ToolService.register("auth_list_roles", LIST_ROLES_DEFINITION)
async def auth_list_roles(params: dict, context: dict) -> dict:
    """List roles from the auth service."""
    base_url = _get_base_url(context)
    if not base_url:
        return {"error": "Auth base URL not configured"}

    tool_service: ToolService = context["tool_service"]
    client, effective_url, should_close = await get_service_client(tool_service, base_url)

    try:
        query: dict = {}
        if params.get("search"):
            query["search"] = params["search"]
        if params.get("limit"):
            query["limit"] = params["limit"]
        if params.get("offset"):
            query["offset"] = params["offset"]

        response = await client.get(
            f"{effective_url}/admin/api/roles",
            headers=_get_headers(context),
            params=query,
        )
        if response.status_code == 200:
            return response.json()
        return {"error": f"Auth API error {response.status_code}: {response.text[:500]}"}
    finally:
        if should_close:
            await client.aclose()
