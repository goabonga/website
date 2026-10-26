# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""HTTP client for Team API (team.internal)."""

import logging
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
from pydantic import BaseModel

from internal.config import settings

logger = logging.getLogger(__name__)


# =============================================================================
# Response Models
# =============================================================================


class TeamInfo(BaseModel):
    """Team in the team platform."""

    id: str
    name: str
    slug: str
    description: str | None = None
    config: dict = {}
    is_active: bool = True
    created_at: datetime
    updated_at: datetime


class AgentInfo(BaseModel):
    """AI agent in a team."""

    id: str
    name: str
    role: str
    description: str | None = None
    system_prompt: str | None = None
    model: str = "gpt-4o"
    provider: str = "openai"
    config: dict = {}
    is_active: bool = True
    created_at: datetime


class SkillInfo(BaseModel):
    """Skill attached to an agent."""

    id: str
    agent_id: str
    name: str
    description: str
    content: str = ""
    allowed_tools: list[str] = []
    is_active: bool = True
    created_at: datetime


class ToolInfo(BaseModel):
    """Tool from the platform tool catalog."""

    name: str
    description: str = ""
    parameters: dict = {}


class WorkflowInfo(BaseModel):
    """Workflow in a team."""

    id: str
    team_id: str
    name: str
    description: str | None = None
    steps: dict = {}
    status: str = "draft"
    config: dict = {}
    created_at: datetime
    updated_at: datetime


class ConversationInfo(BaseModel):
    """Conversation in the team platform."""

    id: str
    slug: str
    title: str
    type: str = "general"
    status: str = "active"
    extra: dict = {}
    created_at: datetime
    updated_at: datetime


class MessageInfo(BaseModel):
    """Message in a conversation."""

    id: str
    conversation_id: str
    agent_id: str | None = None
    type: str = "message"
    content: dict = {}
    text: str = ""
    visibility: str = "public"
    created_at: datetime


class TaskInfo(BaseModel):
    """Task in a team."""

    id: str
    team_id: str
    agent_id: str | None = None
    workflow_id: str | None = None
    title: str
    description: str = ""
    status: str = "pending"
    priority: int = 0
    input_data: dict = {}
    output_data: dict = {}
    created_at: datetime
    updated_at: datetime


class MemoryEntryInfo(BaseModel):
    """Memory entry in a team."""

    id: str
    team_id: str | None = None
    agent_id: str | None = None
    conversation_id: str | None = None
    content: str
    extra: dict = {}
    created_at: datetime


# =============================================================================
# Team Client
# =============================================================================


class TeamClient:
    """HTTP client to interact with team API."""

    def __init__(self) -> None:
        self._socket_path = getattr(settings, "team_socket_path", "") or ""
        if self._socket_path:
            self._base_url = "http://localhost"
        else:
            self._base_url = getattr(settings, "team_api_url", "https://team.internal").rstrip("/")
        self._client_id = settings.oauth2_client_id
        self._client_secret = settings.oauth2_client_secret
        self._issuer = settings.oauth2_issuer.rstrip("/") if settings.oauth2_issuer else ""
        self._tokens: dict[str, tuple[str, datetime]] = {}

    async def _get_access_token(self, scope: str = "team:platform:read") -> str:
        """Get access token using client credentials flow."""
        if scope in self._tokens:
            token, expires_at = self._tokens[scope]
            if datetime.now(UTC) < expires_at - timedelta(seconds=30):
                return token

        if not self._issuer:
            raise ValueError("oauth2_issuer not configured")

        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self._issuer}/oauth2/token",
                data={
                    "grant_type": "client_credentials",
                    "client_id": self._client_id,
                    "client_secret": self._client_secret,
                    "scope": scope,
                },
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
            response.raise_for_status()
            data = response.json()

        access_token = data["access_token"]
        expires_in = data.get("expires_in", 3600)
        expires_at = datetime.now(UTC) + timedelta(seconds=expires_in)
        self._tokens[scope] = (access_token, expires_at)
        return access_token

    async def _request(
        self,
        method: str,
        endpoint: str,
        params: dict[str, Any] | None = None,
        json_data: dict[str, Any] | None = None,
        scope: str = "team:platform:read",
    ) -> Any:
        """Make an authenticated request to the team API."""
        if not self._base_url:
            raise ValueError("team_api_url not configured")

        try:
            token = await self._get_access_token(scope=scope)
        except Exception as e:
            logger.error("Failed to get access token for team API: %s", e)
            raise

        transport = None
        if self._socket_path:
            transport = httpx.AsyncHTTPTransport(uds=self._socket_path)

        async with httpx.AsyncClient(timeout=30.0, transport=transport) as client:
            response = await client.request(
                method,
                f"{self._base_url}{endpoint}",
                params=params,
                json=json_data,
                headers={"Authorization": f"Bearer {token}"},
            )
            response.raise_for_status()
            if response.status_code == 204:
                return None
            return response.json()

    # =========================================================================
    # Teams
    # =========================================================================

    async def list_teams(self, limit: int = 100, offset: int = 0) -> list[TeamInfo]:
        """List all teams."""
        try:
            data = await self._request(
                "GET", "/platform/team", params={"limit": limit, "offset": offset}
            )
            return [TeamInfo(**item) for item in data]
        except Exception as e:
            logger.exception("Failed to fetch teams: %s", e)
            return []

    async def get_team(self, team_id: str) -> TeamInfo | None:
        """Get a specific team."""
        try:
            data = await self._request("GET", f"/platform/team/{team_id}")
            return TeamInfo(**data)
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                return None
            logger.exception("Failed to fetch team: %s", e)
            return None
        except Exception as e:
            logger.exception("Failed to fetch team: %s", e)
            return None

    async def create_team(
        self,
        name: str,
        slug: str,
        description: str | None = None,
        config: dict | None = None,
    ) -> TeamInfo | None:
        """Create a new team."""
        try:
            json_data: dict[str, Any] = {
                "name": name,
                "slug": slug,
                "description": description or "",
                "config": config or {},
            }
            data = await self._request(
                "POST",
                "/platform/team",
                json_data=json_data,
                scope="team:platform:write",
            )
            return TeamInfo(**data)
        except Exception as e:
            logger.exception("Failed to create team: %s", e)
            return None

    async def update_team(
        self,
        team_id: str,
        name: str | None = None,
        description: str | None = None,
        config: dict | None = None,
        is_active: bool | None = None,
    ) -> TeamInfo | None:
        """Update a team."""
        try:
            update_data: dict[str, Any] = {}
            if name is not None:
                update_data["name"] = name
            if description is not None:
                update_data["description"] = description
            if config is not None:
                update_data["config"] = config
            if is_active is not None:
                update_data["is_active"] = is_active

            data = await self._request(
                "PATCH",
                f"/platform/team/{team_id}",
                json_data=update_data,
                scope="team:platform:write",
            )
            return TeamInfo(**data)
        except Exception as e:
            logger.exception("Failed to update team: %s", e)
            return None

    async def delete_team(self, team_id: str) -> bool:
        """Delete a team."""
        try:
            await self._request(
                "DELETE",
                f"/platform/team/{team_id}",
                scope="team:platform:write",
            )
            return True
        except Exception as e:
            logger.exception("Failed to delete team: %s", e)
            return False

    # =========================================================================
    # Agents
    # =========================================================================

    async def list_agents(self, team_id: str, limit: int = 100, offset: int = 0) -> list[AgentInfo]:
        """List agents for a team."""
        try:
            data = await self._request(
                "GET",
                f"/platform/{team_id}/agents",
                params={"limit": limit, "offset": offset},
            )
            return [AgentInfo(**item) for item in data]
        except Exception as e:
            logger.exception("Failed to fetch agents: %s", e)
            return []

    async def get_agent(self, team_id: str, agent_id: str) -> AgentInfo | None:
        """Get a specific agent."""
        try:
            data = await self._request("GET", f"/platform/{team_id}/agents/{agent_id}")
            return AgentInfo(**data)
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                return None
            logger.exception("Failed to fetch agent: %s", e)
            return None
        except Exception as e:
            logger.exception("Failed to fetch agent: %s", e)
            return None

    async def create_agent(
        self,
        team_id: str,
        name: str,
        role: str,
        description: str | None = None,
        system_prompt: str | None = None,
        model: str = "gpt-4o",
        provider: str = "openai",
        config: dict | None = None,
    ) -> AgentInfo | None:
        """Create a new agent."""
        try:
            json_data: dict[str, Any] = {
                "name": name,
                "role": role,
                "description": description or "",
                "system_prompt": system_prompt or "",
                "model": model,
                "provider": provider,
                "config": config or {},
            }
            data = await self._request(
                "POST",
                f"/platform/{team_id}/agents",
                json_data=json_data,
                scope="team:platform:write",
            )
            return AgentInfo(**data)
        except Exception as e:
            logger.exception("Failed to create agent: %s", e)
            return None

    async def update_agent(
        self,
        team_id: str,
        agent_id: str,
        name: str | None = None,
        role: str | None = None,
        description: str | None = None,
        system_prompt: str | None = None,
        model: str | None = None,
        provider: str | None = None,
        config: dict | None = None,
        is_active: bool | None = None,
    ) -> AgentInfo | None:
        """Update an agent."""
        try:
            update_data: dict[str, Any] = {}
            if name is not None:
                update_data["name"] = name
            if role is not None:
                update_data["role"] = role
            if description is not None:
                update_data["description"] = description
            if system_prompt is not None:
                update_data["system_prompt"] = system_prompt
            if model is not None:
                update_data["model"] = model
            if provider is not None:
                update_data["provider"] = provider
            if config is not None:
                update_data["config"] = config
            if is_active is not None:
                update_data["is_active"] = is_active

            data = await self._request(
                "PATCH",
                f"/platform/{team_id}/agents/{agent_id}",
                json_data=update_data,
                scope="team:platform:write",
            )
            return AgentInfo(**data)
        except Exception as e:
            logger.exception("Failed to update agent: %s", e)
            return None

    async def delete_agent(self, team_id: str, agent_id: str) -> bool:
        """Delete an agent."""
        try:
            await self._request(
                "DELETE",
                f"/platform/{team_id}/agents/{agent_id}",
                scope="team:platform:write",
            )
            return True
        except Exception as e:
            logger.exception("Failed to delete agent: %s", e)
            return False

    # =========================================================================
    # Tools (read-only catalog)
    # =========================================================================

    async def list_tools(self) -> list[ToolInfo]:
        """List all available tools from the platform catalog."""
        try:
            data = await self._request("GET", "/platform/tools")
            return [ToolInfo(**item) for item in data]
        except Exception as e:
            logger.exception("Failed to fetch tools: %s", e)
            return []

    # =========================================================================
    # Skills
    # =========================================================================

    async def list_skills(self, team_id: str, agent_id: str) -> list[SkillInfo]:
        """List skills for an agent."""
        try:
            data = await self._request(
                "GET",
                f"/platform/{team_id}/agents/{agent_id}/skills",
            )
            return [SkillInfo(**item) for item in data]
        except Exception as e:
            logger.exception("Failed to fetch skills: %s", e)
            return []

    async def get_skill(
        self,
        team_id: str,
        agent_id: str,
        skill_id: str,
    ) -> SkillInfo | None:
        """Get a single skill by ID."""
        try:
            data = await self._request(
                "GET",
                f"/platform/{team_id}/agents/{agent_id}/skills/{skill_id}",
            )
            return SkillInfo(**data)
        except Exception as e:
            logger.exception("Failed to fetch skill: %s", e)
            return None

    async def create_skill(
        self,
        team_id: str,
        agent_id: str,
        name: str,
        description: str,
        content: str = "",
        allowed_tools: list[str] | None = None,
    ) -> SkillInfo | None:
        """Create a new skill for an agent."""
        try:
            json_data: dict[str, Any] = {
                "name": name,
                "description": description,
                "content": content,
                "allowed_tools": allowed_tools or [],
            }
            data = await self._request(
                "POST",
                f"/platform/{team_id}/agents/{agent_id}/skills",
                json_data=json_data,
                scope="team:platform:write",
            )
            return SkillInfo(**data)
        except Exception as e:
            logger.exception("Failed to create skill: %s", e)
            return None

    async def update_skill(
        self,
        team_id: str,
        agent_id: str,
        skill_id: str,
        name: str | None = None,
        description: str | None = None,
        content: str | None = None,
        allowed_tools: list[str] | None = None,
        is_active: bool | None = None,
    ) -> SkillInfo | None:
        """Update a skill."""
        try:
            update_data: dict[str, Any] = {}
            if name is not None:
                update_data["name"] = name
            if description is not None:
                update_data["description"] = description
            if content is not None:
                update_data["content"] = content
            if allowed_tools is not None:
                update_data["allowed_tools"] = allowed_tools
            if is_active is not None:
                update_data["is_active"] = is_active

            data = await self._request(
                "PATCH",
                f"/platform/{team_id}/agents/{agent_id}/skills/{skill_id}",
                json_data=update_data,
                scope="team:platform:write",
            )
            return SkillInfo(**data)
        except Exception as e:
            logger.exception("Failed to update skill: %s", e)
            return None

    async def delete_skill(self, team_id: str, agent_id: str, skill_id: str) -> bool:
        """Delete a skill."""
        try:
            await self._request(
                "DELETE",
                f"/platform/{team_id}/agents/{agent_id}/skills/{skill_id}",
                scope="team:platform:write",
            )
            return True
        except Exception as e:
            logger.exception("Failed to delete skill: %s", e)
            return False

    # =========================================================================
    # Workflows
    # =========================================================================

    async def list_workflows(
        self, team_id: str, limit: int = 100, offset: int = 0
    ) -> list[WorkflowInfo]:
        """List workflows for a team."""
        try:
            data = await self._request(
                "GET",
                f"/platform/{team_id}/workflows",
                params={"limit": limit, "offset": offset},
            )
            return [WorkflowInfo(**item) for item in data]
        except Exception as e:
            logger.exception("Failed to fetch workflows: %s", e)
            return []

    async def create_workflow(
        self,
        team_id: str,
        name: str,
        description: str | None = None,
        steps: dict | None = None,
        config: dict | None = None,
    ) -> WorkflowInfo | None:
        """Create a new workflow."""
        try:
            json_data: dict[str, Any] = {
                "name": name,
                "description": description or "",
                "steps": steps or {},
                "config": config or {},
            }
            data = await self._request(
                "POST",
                f"/platform/{team_id}/workflows",
                json_data=json_data,
                scope="team:platform:write",
            )
            return WorkflowInfo(**data)
        except Exception as e:
            logger.exception("Failed to create workflow: %s", e)
            return None

    async def update_workflow(
        self,
        team_id: str,
        workflow_id: str,
        name: str | None = None,
        description: str | None = None,
        steps: dict | None = None,
        status: str | None = None,
        config: dict | None = None,
    ) -> WorkflowInfo | None:
        """Update a workflow."""
        try:
            update_data: dict[str, Any] = {}
            if name is not None:
                update_data["name"] = name
            if description is not None:
                update_data["description"] = description
            if steps is not None:
                update_data["steps"] = steps
            if status is not None:
                update_data["status"] = status
            if config is not None:
                update_data["config"] = config

            data = await self._request(
                "PATCH",
                f"/platform/{team_id}/workflows/{workflow_id}",
                json_data=update_data,
                scope="team:platform:write",
            )
            return WorkflowInfo(**data)
        except Exception as e:
            logger.exception("Failed to update workflow: %s", e)
            return None

    async def delete_workflow(self, team_id: str, workflow_id: str) -> bool:
        """Delete a workflow."""
        try:
            await self._request(
                "DELETE",
                f"/platform/{team_id}/workflows/{workflow_id}",
                scope="team:platform:write",
            )
            return True
        except Exception as e:
            logger.exception("Failed to delete workflow: %s", e)
            return False

    # =========================================================================
    # Conversations
    # =========================================================================

    async def list_conversations(self, limit: int = 100, offset: int = 0) -> list[ConversationInfo]:
        """List all conversations."""
        try:
            data = await self._request(
                "GET",
                "/platform/conversations",
                params={"limit": limit, "offset": offset},
            )
            return [ConversationInfo(**item) for item in data]
        except Exception as e:
            logger.exception("Failed to fetch conversations: %s", e)
            return []

    async def get_conversation(self, conversation_id: str) -> ConversationInfo | None:
        """Get a specific conversation."""
        try:
            data = await self._request("GET", f"/platform/conversations/{conversation_id}")
            return ConversationInfo(**data)
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                return None
            logger.exception("Failed to fetch conversation: %s", e)
            return None
        except Exception as e:
            logger.exception("Failed to fetch conversation: %s", e)
            return None

    async def create_conversation(
        self,
        slug: str,
        title: str,
        conv_type: str = "general",
        extra: dict | None = None,
    ) -> ConversationInfo | None:
        """Create a new conversation."""
        try:
            json_data: dict[str, Any] = {
                "slug": slug,
                "title": title,
                "type": conv_type,
                "extra": extra or {},
            }
            data = await self._request(
                "POST",
                "/platform/conversations",
                json_data=json_data,
                scope="team:platform:write",
            )
            return ConversationInfo(**data)
        except Exception as e:
            logger.exception("Failed to create conversation: %s", e)
            return None

    async def delete_conversation(self, conversation_id: str) -> bool:
        """Delete a conversation."""
        try:
            await self._request(
                "DELETE",
                f"/platform/conversations/{conversation_id}",
                scope="team:platform:write",
            )
            return True
        except Exception as e:
            logger.exception("Failed to delete conversation: %s", e)
            return False

    async def add_agent_to_conversation(self, conversation_id: str, agent_id: str) -> bool:
        """Add an agent to a conversation."""
        try:
            await self._request(
                "POST",
                f"/platform/conversations/{conversation_id}/agents/{agent_id}",
                scope="team:platform:write",
            )
            return True
        except Exception as e:
            logger.exception("Failed to add agent to conversation: %s", e)
            return False

    # =========================================================================
    # Messages
    # =========================================================================

    async def list_messages(
        self, conversation_id: str, limit: int = 100, offset: int = 0
    ) -> list[MessageInfo]:
        """List messages in a conversation."""
        try:
            data = await self._request(
                "GET",
                f"/platform/conversations/{conversation_id}/messages",
                params={"limit": limit, "offset": offset},
                scope="team:read",
            )
            return [MessageInfo(**item) for item in data]
        except Exception as e:
            logger.exception("Failed to fetch messages: %s", e)
            return []

    async def create_message(
        self,
        conversation_id: str,
        agent_id: str,
        text: str,
        msg_type: str = "message",
        content: dict | None = None,
        visibility: str = "public",
    ) -> MessageInfo | None:
        """Create a message in a conversation."""
        try:
            json_data: dict[str, Any] = {
                "agent_id": agent_id,
                "type": msg_type,
                "content": content or {},
                "text": text,
                "visibility": visibility,
            }
            data = await self._request(
                "POST",
                f"/platform/conversations/{conversation_id}/messages",
                json_data=json_data,
                scope="team:write",
            )
            return MessageInfo(**data)
        except Exception as e:
            logger.exception("Failed to create message: %s", e)
            return None

    # =========================================================================
    # Tasks
    # =========================================================================

    async def create_task(
        self,
        team_id: str,
        title: str,
        description: str = "",
        agent_id: str | None = None,
        input_data: dict | None = None,
        priority: int = 0,
    ) -> TaskInfo | None:
        """Create a task. If agent_id is provided, the task is assigned and executed immediately."""
        try:
            json_data: dict[str, Any] = {
                "title": title,
                "description": description,
                "priority": priority,
                "input_data": input_data or {},
            }
            if agent_id:
                json_data["agent_id"] = agent_id

            data = await self._request(
                "POST",
                f"/platform/{team_id}/tasks",
                json_data=json_data,
                scope="team:platform:write",
            )
            return TaskInfo(**data)
        except Exception as e:
            logger.exception("Failed to create task: %s", e)
            return None

    async def cancel_task(self, team_id: str, task_id: str) -> bool:
        """Cancel a task."""
        try:
            await self._request(
                "POST",
                f"/platform/{team_id}/tasks/{task_id}/cancel",
                scope="team:platform:write",
            )
            return True
        except Exception as e:
            logger.exception("Failed to cancel task: %s", e)
            return False

    # =========================================================================
    # Memory
    # =========================================================================

    async def list_memory(
        self, team_id: str, limit: int = 100, offset: int = 0
    ) -> list[MemoryEntryInfo]:
        """List memory entries for a team."""
        try:
            data = await self._request(
                "GET",
                f"/platform/{team_id}/memory",
                params={"limit": limit, "offset": offset},
            )
            return [MemoryEntryInfo(**item) for item in data]
        except Exception as e:
            logger.exception("Failed to fetch memory entries: %s", e)
            return []

    async def create_memory(
        self,
        team_id: str,
        content: str,
        agent_id: str | None = None,
        conversation_id: str | None = None,
        extra: dict | None = None,
    ) -> MemoryEntryInfo | None:
        """Create a memory entry."""
        try:
            json_data: dict[str, Any] = {
                "content": content,
                "extra": extra or {},
            }
            if agent_id:
                json_data["agent_id"] = agent_id
            if conversation_id:
                json_data["conversation_id"] = conversation_id

            data = await self._request(
                "POST",
                f"/platform/{team_id}/memory",
                json_data=json_data,
                scope="team:platform:write",
            )
            return MemoryEntryInfo(**data)
        except Exception as e:
            logger.exception("Failed to create memory entry: %s", e)
            return None

    async def delete_memory(self, team_id: str, memory_id: str) -> bool:
        """Delete a memory entry."""
        try:
            await self._request(
                "DELETE",
                f"/platform/{team_id}/memory/{memory_id}",
                scope="team:platform:write",
            )
            return True
        except Exception as e:
            logger.exception("Failed to delete memory entry: %s", e)
            return False


# Singleton instance
team_client = TeamClient()
