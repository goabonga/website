# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for Celery task utilities."""

import asyncio

from team.tasks.utils import run_async


class TestRunAsync:
    def test_runs_coroutine(self):
        async def add(a: int, b: int) -> int:
            return a + b

        result = run_async(add(2, 3))
        assert result == 5

    def test_runs_async_with_await(self):
        async def delayed_value() -> str:
            await asyncio.sleep(0)
            return "done"

        result = run_async(delayed_value())
        assert result == "done"

    def test_propagates_exception(self):
        async def fail() -> None:
            raise ValueError("boom")

        try:
            run_async(fail())
            raise AssertionError("Should have raised")
        except ValueError as e:
            assert str(e) == "boom"
