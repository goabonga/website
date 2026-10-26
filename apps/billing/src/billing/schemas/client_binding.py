# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Client binding schemas."""

from datetime import datetime

from pydantic import BaseModel


class ClientBindingResponse(BaseModel):
    """An OAuth client allowed to act on a SaaS application."""

    id: str
    saas_app_id: str
    client_id: str
    created_at: datetime

    model_config = {"from_attributes": True}


class ClientSaasResponse(BaseModel):
    """The SaaS applications an OAuth client is bound to."""

    client_id: str
    saas_ids: list[str]
