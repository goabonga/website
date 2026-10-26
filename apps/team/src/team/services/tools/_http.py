# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Shared HTTP helpers for service tools.

Supports both standard HTTP URLs and Unix domain sockets:
  - http://billing.internal  → regular HTTP connection
  - unix:///run/billing/billing.sock  → UDS transport via httpx
"""

import httpx

from team.services.tool_service import ToolService


async def get_service_client(
    tool_service: ToolService, base_url: str
) -> tuple[httpx.AsyncClient, str, bool]:
    """Return (client, effective_base_url, should_close).

    When *base_url* starts with ``unix://``, a dedicated httpx client with a
    UDS transport is created.  The caller **must** close it after use (the
    third element will be ``True``).

    For regular HTTP URLs the shared ``tool_service`` client is reused and the
    caller must **not** close it.
    """
    if base_url.startswith("unix://"):
        socket_path = base_url[len("unix://") :]
        transport = httpx.AsyncHTTPTransport(uds=socket_path)
        client = httpx.AsyncClient(transport=transport)
        return client, "http://localhost", True

    return await tool_service.get_client(), base_url, False
