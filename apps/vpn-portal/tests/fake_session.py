# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""An in-memory stand-in for ``AsyncSession``.

It understands exactly the statements the portal issues (``select`` of a model or of a
``count``, filtered with ``==``, ``IS NULL``, ``>`` and ``AND``, ordered, limited and
offset) and keeps rows as plain model instances, so the services and routes run their
real code without a database. It is shared by the pytest suite and the behave steps.
"""

from __future__ import annotations

import operator
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.sql import operators
from sqlalchemy.sql.elements import BooleanClauseList, Null

COMPARISONS = {
    "eq": operator.eq,
    "ne": operator.ne,
    "gt": operator.gt,
    "ge": operator.ge,
    "lt": operator.lt,
    "le": operator.le,
}


class FakeResult:
    """The subset of ``Result`` used by the portal."""

    def __init__(self, rows: list[Any], is_count: bool = False) -> None:
        self._rows = rows
        self._is_count = is_count

    def scalar(self) -> Any:
        if self._is_count:
            return len(self._rows)
        return self._rows[0] if self._rows else None

    def scalar_one_or_none(self) -> Any:
        if len(self._rows) > 1:
            raise RuntimeError("Multiple rows were found when one or none was required")
        return self._rows[0] if self._rows else None

    def scalars(self) -> FakeResult:
        return self

    def first(self) -> Any:
        return self._rows[0] if self._rows else None

    def all(self) -> list[Any]:
        return list(self._rows)


def _matches(row: Any, clause: Any) -> bool:
    if clause is None:
        return True
    if isinstance(clause, BooleanClauseList):
        combine = all if clause.operator is operators.and_ else any
        return combine(_matches(row, part) for part in clause.clauses)
    value = getattr(row, clause.left.key)
    name = clause.operator.__name__
    if isinstance(clause.right, Null):
        return (value is None) if name == "is_" else (value is not None)
    expected = clause.right.value
    if name in COMPARISONS:
        return value is not None and COMPARISONS[name](value, expected)
    raise NotImplementedError(f"unsupported operator: {name}")


class FakeSession:
    """Stores rows per table name; commit moves pending objects into the store."""

    def __init__(self) -> None:
        self.tables: dict[str, list[Any]] = {}
        self._pending: list[Any] = []
        self.commits = 0
        self.closed = False

    def rows(self, table: str) -> list[Any]:
        return self.tables.setdefault(table, [])

    # -- session API -------------------------------------------------------------------

    def add(self, obj: Any) -> None:
        self._pending.append(obj)

    async def commit(self) -> None:
        for obj in self._pending:
            self._apply_defaults(obj)
            self.rows(obj.__table__.name).append(obj)
        self._pending.clear()
        self.commits += 1

    async def refresh(self, obj: Any) -> None:
        self._apply_defaults(obj)

    async def close(self) -> None:
        self.closed = True

    async def execute(self, statement: Any) -> FakeResult:
        table = statement.get_final_froms()[0].name
        rows = [row for row in self.rows(table) if _matches(row, statement.whereclause)]

        for clause in reversed(statement._order_by_clauses):
            column = getattr(clause, "element", clause)
            descending = (
                clause.modifier is operators.desc_op if hasattr(clause, "modifier") else False
            )
            rows.sort(key=lambda row, name=column.key: getattr(row, name), reverse=descending)

        offset = statement._offset or 0
        limit = statement._limit
        rows = rows[offset:] if limit is None else rows[offset : offset + limit]

        first_column = statement.selected_columns[0]
        return FakeResult(rows, is_count=str(first_column).startswith("count("))

    # -- helpers -----------------------------------------------------------------------

    @staticmethod
    def _apply_defaults(obj: Any) -> None:
        now = datetime.now(UTC)
        for name in ("created_at", "updated_at"):
            if hasattr(obj, name) and getattr(obj, name) is None:
                setattr(obj, name, now)
        if hasattr(obj, "id") and obj.id is None:
            obj.id = uuid.uuid4()
        for name in ("bytes_received", "bytes_sent"):
            if hasattr(obj, name) and getattr(obj, name) is None:
                setattr(obj, name, 0)
