# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Steps for the browser scenarios of the knowledge namespaces."""

from behave import given, when
from internal.models.knowledge import KnowledgeNamespace


@given('{count:d} namespaces named "{prefix}" exist')
def step_many_namespaces(context, count, prefix):
    async def _create():
        async with context.session_maker() as session:
            for index in range(count):
                session.add(
                    KnowledgeNamespace(
                        slug=f"bulk-{index:03d}", name=f"{prefix} {index:03d}", is_public=True
                    )
                )
            await session.commit()

    context.loop.run_until_complete(_create())


@when("I open the namespace I created")
def step_open_namespace(context):
    context.page.goto(f"{context.base_url}/namespaces/{context.ns_namespace_id}")


@when("I open the edit form of the namespace I created")
def step_open_namespace_edit(context):
    context.page.goto(f"{context.base_url}/namespaces/{context.ns_namespace_id}/edit")
