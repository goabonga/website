# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Step definitions for the data reset feature."""

from analytics.models import Base
from behave import given, then
from sqlalchemy import func, select


@given("the pixel is opened and the campaign link is clicked")
def step_open_and_click(context):
    context.execute_steps(
        """
        When I send a GET request to the pixel URL
        And I send a GET request to the campaign link
        """
    )


@then("the database should be empty")
def step_database_empty(context):
    async def counts():
        async with context.session_maker() as db:
            return {
                table.name: (await db.execute(select(func.count()).select_from(table))).scalar_one()
                for table in Base.metadata.sorted_tables
            }

    remaining = context.loop.run_until_complete(counts())
    assert not any(remaining.values()), remaining
