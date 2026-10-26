# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class ExecutionLogResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    team_id: UUID
    task_id: UUID | None
    workflow_id: UUID | None
    agent_id: UUID | None
    event_type: str
    details: dict
    created_at: datetime
