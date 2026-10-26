# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Billing service tools — subscriptions, customers, and usage reporting."""

from team.config import get_settings
from team.services.tool_service import ToolService
from team.services.tools._http import get_service_client


def _get_base_url(context: dict) -> str:
    """Resolve billing base URL: agent credentials first, then global settings."""
    agent_config = context.get("agent_config", {})
    url = agent_config.get("credentials", {}).get("billing_base_url", "")
    if url:
        return url
    return get_settings().billing_base_url


def _get_headers(context: dict) -> dict:
    """Build authorization headers for the billing service."""
    agent_config = context.get("agent_config", {})
    token = agent_config.get("credentials", {}).get("billing_token", "")
    if not token:
        token = get_settings().oauth2_client_secret
    return {"Authorization": f"Bearer {token}"}


# --- billing_list_subscriptions ---

LIST_SUBSCRIPTIONS_DEFINITION = {
    "name": "billing_list_subscriptions",
    "description": "List subscriptions for a SaaS application on the billing platform.",
    "parameters": {
        "type": "object",
        "properties": {
            "saas_id": {"type": "string", "description": "SaaS application ID"},
            "status_filter": {
                "type": "string",
                "description": "Filter by status (active, canceled, past_due)",
            },
            "limit": {"type": "integer", "description": "Max results to return", "default": 50},
        },
        "required": ["saas_id"],
    },
}


@ToolService.register("billing_list_subscriptions", LIST_SUBSCRIPTIONS_DEFINITION)
async def billing_list_subscriptions(params: dict, context: dict) -> dict:
    """List subscriptions for a SaaS app."""
    base_url = _get_base_url(context)
    if not base_url:
        return {"error": "Billing base URL not configured"}

    tool_service: ToolService = context["tool_service"]
    client, effective_url, should_close = await get_service_client(tool_service, base_url)

    try:
        query: dict = {}
        if params.get("status_filter"):
            query["status"] = params["status_filter"]
        if params.get("limit"):
            query["limit"] = params["limit"]

        response = await client.get(
            f"{effective_url}/platform/{params['saas_id']}/subscriptions",
            headers=_get_headers(context),
            params=query,
        )
        if response.status_code == 200:
            return response.json()
        return {"error": f"Billing API error {response.status_code}: {response.text[:500]}"}
    finally:
        if should_close:
            await client.aclose()


# --- billing_get_customer ---

GET_CUSTOMER_DEFINITION = {
    "name": "billing_get_customer",
    "description": "Get customer details from the billing platform.",
    "parameters": {
        "type": "object",
        "properties": {
            "saas_id": {"type": "string", "description": "SaaS application ID"},
            "customer_id": {"type": "string", "description": "Customer ID"},
        },
        "required": ["saas_id", "customer_id"],
    },
}


@ToolService.register("billing_get_customer", GET_CUSTOMER_DEFINITION)
async def billing_get_customer(params: dict, context: dict) -> dict:
    """Get a customer by ID."""
    base_url = _get_base_url(context)
    if not base_url:
        return {"error": "Billing base URL not configured"}

    tool_service: ToolService = context["tool_service"]
    client, effective_url, should_close = await get_service_client(tool_service, base_url)

    try:
        response = await client.get(
            f"{effective_url}/platform/{params['saas_id']}/customers/{params['customer_id']}",
            headers=_get_headers(context),
        )
        if response.status_code == 200:
            return response.json()
        return {"error": f"Billing API error {response.status_code}: {response.text[:500]}"}
    finally:
        if should_close:
            await client.aclose()


# --- billing_report_usage ---

REPORT_USAGE_DEFINITION = {
    "name": "billing_report_usage",
    "description": "Report a usage event for metered billing.",
    "parameters": {
        "type": "object",
        "properties": {
            "saas_id": {"type": "string", "description": "SaaS application ID"},
            "subscription_id": {"type": "string", "description": "Subscription ID"},
            "quantity": {"type": "integer", "description": "Usage quantity to report"},
            "action": {
                "type": "string",
                "description": "Usage action type (increment, set)",
                "default": "increment",
            },
        },
        "required": ["saas_id", "subscription_id", "quantity"],
    },
}


@ToolService.register("billing_report_usage", REPORT_USAGE_DEFINITION)
async def billing_report_usage(params: dict, context: dict) -> dict:
    """Report a usage event."""
    base_url = _get_base_url(context)
    if not base_url:
        return {"error": "Billing base URL not configured"}

    tool_service: ToolService = context["tool_service"]
    client, effective_url, should_close = await get_service_client(tool_service, base_url)

    try:
        payload: dict = {
            "subscription_id": params["subscription_id"],
            "quantity": params["quantity"],
        }
        if params.get("action"):
            payload["action"] = params["action"]

        response = await client.post(
            f"{effective_url}/usage/{params['saas_id']}/report",
            headers=_get_headers(context),
            json=payload,
        )
        if response.status_code in (200, 201):
            return response.json()
        return {"error": f"Billing API error {response.status_code}: {response.text[:500]}"}
    finally:
        if should_close:
            await client.aclose()


# --- billing_get_subscription ---

GET_SUBSCRIPTION_DEFINITION = {
    "name": "billing_get_subscription",
    "description": "Get subscription details from the billing platform.",
    "parameters": {
        "type": "object",
        "properties": {
            "saas_id": {"type": "string", "description": "SaaS application ID"},
            "subscription_id": {"type": "string", "description": "Subscription ID"},
        },
        "required": ["saas_id", "subscription_id"],
    },
}


@ToolService.register("billing_get_subscription", GET_SUBSCRIPTION_DEFINITION)
async def billing_get_subscription(params: dict, context: dict) -> dict:
    """Get a subscription by ID."""
    base_url = _get_base_url(context)
    if not base_url:
        return {"error": "Billing base URL not configured"}

    tool_service: ToolService = context["tool_service"]
    client, effective_url, should_close = await get_service_client(tool_service, base_url)

    try:
        response = await client.get(
            f"{effective_url}/platform/{params['saas_id']}/subscriptions/{params['subscription_id']}",
            headers=_get_headers(context),
        )
        if response.status_code == 200:
            return response.json()
        return {"error": f"Billing API error {response.status_code}: {response.text[:500]}"}
    finally:
        if should_close:
            await client.aclose()
