# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Steps for the browser scenarios of the system prompts."""

from behave import given, when
from internal.models.prompt import SystemPrompt, SystemPromptVersion


@given('{count:d} prompts named "{prefix}" exist')
def step_many_prompts(context, count, prefix):
    async def _create():
        async with context.session_maker() as session:
            for index in range(count):
                prompt = SystemPrompt(
                    slug=f"bulk-{index:03d}", name=f"{prefix} {index:03d}", is_default=False
                )
                session.add(prompt)
                await session.flush()
                session.add(
                    SystemPromptVersion(
                        prompt_id=prompt.id,
                        version=1,
                        content=f"Content {index}",
                        metadata_={},
                        is_current=True,
                    )
                )
            await session.commit()

    context.loop.run_until_complete(_create())


@when("I open the prompt I created")
def step_open_prompt(context):
    context.page.goto(f"{context.base_url}/prompts/{context.prompt_id}")


@when("I open the edit form of the prompt I created")
def step_open_prompt_edit(context):
    context.page.goto(f"{context.base_url}/prompts/{context.prompt_id}/edit")
