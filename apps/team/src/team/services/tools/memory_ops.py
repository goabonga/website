# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Memory tools — save, search, update, and delete team memory entries."""

import logging

from sqlalchemy import select

from team.models import MemoryEntry
from team.services.embeddings import generate_embedding
from team.services.tool_service import ToolService

logger = logging.getLogger(__name__)


# --- save_memory ---

SAVE_DEFINITION = {
    "name": "save_memory",
    "description": (
        "Save a piece of information to the team's long-term memory. "
        "The content will be embedded for later semantic search via search_memory."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "content": {
                "type": "string",
                "description": "The information to remember (plain text)",
            },
            "extra": {
                "type": "object",
                "description": "Optional metadata (e.g., source, category, tags)",
            },
        },
        "required": ["content"],
    },
}


@ToolService.register("save_memory", SAVE_DEFINITION)
async def save_memory(params: dict, context: dict) -> dict:
    """Save content to team memory with its vector embedding."""
    session = context["db"]
    team_id = context["team_id"]
    agent_id = context.get("agent_id")
    content = params["content"]
    extra = params.get("extra", {})

    embedding = await generate_embedding(content)

    entry = MemoryEntry(
        team_id=team_id,
        agent_id=agent_id,
        content=content,
        extra=extra,
        embedding=embedding,
    )
    session.add(entry)
    await session.flush()
    await session.refresh(entry)

    logger.info(f"Saved memory entry {entry.id} for team {team_id}")
    return {
        "saved": True,
        "memory_id": str(entry.id),
        "content_length": len(content),
    }


# --- search_memory ---

SEARCH_DEFINITION = {
    "name": "search_memory",
    "description": "Search team memory entries by semantic similarity (vector search) with keyword fallback.",
    "parameters": {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Search text"},
            "limit": {"type": "integer", "description": "Max results", "default": 5},
        },
        "required": ["query"],
    },
}


@ToolService.register("search_memory", SEARCH_DEFINITION)
async def search_memory(params: dict, context: dict) -> dict:
    """Search memory using vector cosine similarity, falling back to ILIKE."""
    session = context["db"]
    team_id = context["team_id"]
    query = params["query"]
    limit = params.get("limit", 5)

    # Try vector search first
    query_embedding = await generate_embedding(query)
    is_zero = all(v == 0.0 for v in query_embedding)

    if not is_zero:
        # Cosine distance: smaller = more similar
        result = await session.execute(
            select(MemoryEntry)
            .where(MemoryEntry.team_id == team_id)
            .order_by(MemoryEntry.embedding.cosine_distance(query_embedding))
            .limit(limit)
        )
        entries = list(result.scalars().all())
        return {
            "results": [
                {"id": str(e.id), "content": e.content, "created_at": str(e.created_at)}
                for e in entries
            ],
            "search_type": "vector",
        }

    # Fallback to text search when no API key
    logger.info("Falling back to text search (no embedding API key)")
    result = await session.execute(
        select(MemoryEntry)
        .where(MemoryEntry.team_id == team_id, MemoryEntry.content.ilike(f"%{query}%"))
        .limit(limit)
    )
    entries = list(result.scalars().all())
    return {
        "results": [
            {"id": str(e.id), "content": e.content, "created_at": str(e.created_at)}
            for e in entries
        ],
        "search_type": "keyword",
    }


# --- update_memory ---

UPDATE_DEFINITION = {
    "name": "update_memory",
    "description": "Update the content of an existing memory entry. The embedding will be regenerated.",
    "parameters": {
        "type": "object",
        "properties": {
            "memory_id": {"type": "string", "description": "Memory entry ID (UUID)"},
            "content": {
                "type": "string",
                "description": "New content to replace the existing text",
            },
            "extra": {"type": "object", "description": "New metadata (replaces existing)"},
        },
        "required": ["memory_id", "content"],
    },
}


@ToolService.register("update_memory", UPDATE_DEFINITION)
async def update_memory(params: dict, context: dict) -> dict:
    """Update a memory entry's content and re-embed."""
    session = context["db"]
    team_id = context["team_id"]
    memory_id = params["memory_id"]

    result = await session.execute(
        select(MemoryEntry).where(MemoryEntry.id == memory_id, MemoryEntry.team_id == team_id)
    )
    entry = result.scalar_one_or_none()
    if not entry:
        return {"error": f"Memory entry not found: {memory_id}"}

    content = params["content"]
    entry.content = content
    entry.embedding = await generate_embedding(content)
    if "extra" in params:
        entry.extra = params["extra"]

    await session.flush()
    logger.info(f"Updated memory entry {memory_id}")
    return {"updated": True, "memory_id": memory_id}


# --- delete_memory ---

DELETE_DEFINITION = {
    "name": "delete_memory",
    "description": "Delete a memory entry by ID.",
    "parameters": {
        "type": "object",
        "properties": {
            "memory_id": {"type": "string", "description": "Memory entry ID (UUID)"},
        },
        "required": ["memory_id"],
    },
}


@ToolService.register("delete_memory", DELETE_DEFINITION)
async def delete_memory(params: dict, context: dict) -> dict:
    """Delete a memory entry."""
    session = context["db"]
    team_id = context["team_id"]
    memory_id = params["memory_id"]

    result = await session.execute(
        select(MemoryEntry).where(MemoryEntry.id == memory_id, MemoryEntry.team_id == team_id)
    )
    entry = result.scalar_one_or_none()
    if not entry:
        return {"error": f"Memory entry not found: {memory_id}"}

    await session.delete(entry)
    await session.flush()
    logger.info(f"Deleted memory entry {memory_id}")
    return {"deleted": True, "memory_id": memory_id}
