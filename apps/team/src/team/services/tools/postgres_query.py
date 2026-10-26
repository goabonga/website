# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""postgres_query tool — execute read-only SQL queries."""

import re

import asyncpg

from team.config import get_settings
from team.services.tool_service import ToolService

MAX_ROWS = 100

# Patterns that indicate write/DDL operations
_FORBIDDEN_PATTERNS = re.compile(
    r"\b(INSERT|UPDATE|DELETE|DROP|ALTER|CREATE|TRUNCATE|GRANT|REVOKE)\b",
    re.IGNORECASE,
)

DEFINITION = {
    "name": "postgres_query",
    "description": "Execute a read-only SQL query against the database.",
    "parameters": {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "SQL SELECT query"},
        },
        "required": ["query"],
    },
}


def _validate_query(query: str) -> str | None:
    """Validate that the query is a safe read-only SELECT.

    Returns an error message string if invalid, None if valid.
    """
    stripped = query.strip().rstrip(";").strip()
    if not stripped.upper().startswith("SELECT"):
        return "Only SELECT queries are allowed"
    if _FORBIDDEN_PATTERNS.search(stripped):
        return "Query contains forbidden keywords"
    return None


def _asyncpg_dsn(sqlalchemy_url: str) -> str:
    """Convert SQLAlchemy async DSN to plain PostgreSQL DSN for asyncpg."""
    return sqlalchemy_url.replace("postgresql+asyncpg://", "postgresql://")


@ToolService.register("postgres_query", DEFINITION)
async def postgres_query(params: dict, context: dict) -> dict:
    """Execute a read-only SQL query."""
    query = params["query"]

    error = _validate_query(query)
    if error:
        return {"error": error}

    dsn = _asyncpg_dsn(get_settings().database_url)
    conn = await asyncpg.connect(dsn)
    try:
        rows = await conn.fetch(query)
        results = [dict(row) for row in rows[:MAX_ROWS]]
        return {"rows": results, "count": len(results), "truncated": len(rows) > MAX_ROWS}
    finally:
        await conn.close()
