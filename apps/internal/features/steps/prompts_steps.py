# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Step definitions for system prompt management scenarios."""

from unittest.mock import AsyncMock, MagicMock

from behave import given, when
from internal.config import settings as _settings
from internal.models.prompt import SystemPrompt, SystemPromptVersion

# --- Helper ---


def _make_prompt_request(context, method, path, **kwargs):
    """Helper to make HTTP requests with auth cookies."""
    from httpx import ASGITransport, AsyncClient

    cookies = {"access_token": "test-token"} if context.authenticated else {}

    async def _do_request():
        async with AsyncClient(
            transport=ASGITransport(app=context.app),
            base_url="http://test",
            cookies=cookies,
            follow_redirects=False,
        ) as client:
            return await getattr(client, method)(path, **kwargs)

    context.response = context.loop.run_until_complete(_do_request())


# --- Prompt seed data ---


@given('a prompt "{slug}" with name "{name}" exists')
def step_prompt_exists(context, slug, name):
    async def _create():
        async with context.session_maker() as session:
            prompt = SystemPrompt(
                slug=slug,
                name=name,
                description=f"Description for {name}",
                is_default=False,
            )
            session.add(prompt)
            await session.flush()

            version = SystemPromptVersion(
                prompt_id=prompt.id,
                version=1,
                content=f"System prompt content for {name}",
                metadata_={},
                is_current=True,
            )
            session.add(version)
            await session.commit()
            await session.refresh(prompt)
            await session.refresh(version)

            context.prompt_id = prompt.id
            context.current_version_id = version.id
            context.created_ids.append(prompt.id)
            return prompt

    context.loop.run_until_complete(_create())


@given('another prompt "{slug}" with name "{name}" exists')
def step_another_prompt_exists(context, slug, name):
    async def _create():
        async with context.session_maker() as session:
            prompt = SystemPrompt(
                slug=slug,
                name=name,
                description=f"Description for {name}",
                is_default=False,
            )
            session.add(prompt)
            await session.flush()

            version = SystemPromptVersion(
                prompt_id=prompt.id,
                version=1,
                content=f"System prompt content for {name}",
                metadata_={},
                is_current=True,
            )
            session.add(version)
            await session.commit()
            await session.refresh(prompt)

            context.created_ids.append(prompt.id)
            return prompt

    context.loop.run_until_complete(_create())


@given('a prompt "{slug}" with name "{name}" and multiple versions exists')
def step_prompt_with_versions(context, slug, name):
    async def _create():
        async with context.session_maker() as session:
            prompt = SystemPrompt(
                slug=slug,
                name=name,
                description=f"Description for {name}",
                is_default=False,
            )
            session.add(prompt)
            await session.flush()

            # Version 1 (old, not current)
            v1 = SystemPromptVersion(
                prompt_id=prompt.id,
                version=1,
                content=f"Version 1 content for {name}",
                metadata_={},
                is_current=False,
            )
            session.add(v1)

            # Version 2 (current)
            v2 = SystemPromptVersion(
                prompt_id=prompt.id,
                version=2,
                content=f"Version 2 content for {name}",
                metadata_={},
                is_current=True,
            )
            session.add(v2)
            await session.commit()
            await session.refresh(prompt)
            await session.refresh(v1)
            await session.refresh(v2)

            context.prompt_id = prompt.id
            context.current_version_id = v2.id
            context.old_version_id = v1.id
            context.non_current_version_ids = [v1.id]
            context.created_ids.append(prompt.id)
            return prompt

    context.loop.run_until_complete(_create())


@given("a default prompt exists")
def step_default_prompt_exists(context):
    async def _create():
        async with context.session_maker() as session:
            prompt = SystemPrompt(
                slug="default",
                name="Default Assistant",
                description="Default system prompt",
                is_default=True,
            )
            session.add(prompt)
            await session.flush()

            version = SystemPromptVersion(
                prompt_id=prompt.id,
                version=1,
                content="You are a helpful AI assistant.",
                metadata_={},
                is_current=True,
            )
            session.add(version)
            await session.commit()
            await session.refresh(prompt)

            context.prompt_id = prompt.id
            return prompt

    context.loop.run_until_complete(_create())


# --- Prompt generator mock ---


@given("the prompt generator returns data")
def step_prompt_generator_returns(context):
    mock_generator = MagicMock()
    mock_generator.generate_prompt = AsyncMock(
        return_value={
            "name": "Generated Prompt",
            "slug": "generated-prompt",
            "description": "AI-generated prompt",
            "content": "You are a helpful customer support assistant.",
        }
    )
    context.mock_prompt_generator_cls.return_value = mock_generator


# --- Dynamic path request steps ---


@when("I view the prompt detail")
def step_view_prompt_detail(context):
    prompt_id = getattr(context, "prompt_id", 99999)
    _make_prompt_request(context, "get", f"/prompts/{prompt_id}")


@when("I view the prompt edit form")
def step_view_prompt_edit(context):
    prompt_id = getattr(context, "prompt_id", 99999)
    _make_prompt_request(context, "get", f"/prompts/{prompt_id}/edit")


@when("I update the prompt with form data")
def step_update_prompt(context):
    prompt_id = getattr(context, "prompt_id", 99999)
    data = {}
    for row in context.table:
        data[row["field"]] = row["value"]
    _make_prompt_request(context, "post", f"/prompts/{prompt_id}/edit", data=data)


@when("I activate the old prompt version")
def step_activate_version(context):
    prompt_id = getattr(context, "prompt_id", 99999)
    version_id = getattr(context, "old_version_id", 99999)
    _make_prompt_request(context, "post", f"/prompts/{prompt_id}/version/{version_id}/activate")


@when("I delete the old prompt version")
def step_delete_old_version(context):
    prompt_id = getattr(context, "prompt_id", 99999)
    version_id = getattr(context, "old_version_id", 99999)
    _make_prompt_request(context, "post", f"/prompts/{prompt_id}/version/{version_id}/delete")


@when("I delete the current prompt version")
def step_delete_current_version(context):
    prompt_id = getattr(context, "prompt_id", 99999)
    version_id = getattr(context, "current_version_id", 99999)
    _make_prompt_request(context, "post", f"/prompts/{prompt_id}/version/{version_id}/delete")


@when("I delete the prompt")
def step_delete_prompt(context):
    prompt_id = getattr(context, "prompt_id", 99999)
    _make_prompt_request(context, "post", f"/prompts/{prompt_id}/delete")


@when("I bulk delete the created prompts")
def step_bulk_delete_prompts(context):
    from httpx import ASGITransport, AsyncClient

    cookies = {"access_token": "test-token"} if context.authenticated else {}
    files = [("prompt_ids", (None, str(pid))) for pid in context.created_ids]

    async def _do_request():
        async with AsyncClient(
            transport=ASGITransport(app=context.app),
            base_url="http://test",
            cookies=cookies,
            follow_redirects=False,
        ) as client:
            return await client.post("/prompts/bulk-delete", files=files)

    context.response = context.loop.run_until_complete(_do_request())


@when("I bulk delete the non-current prompt versions")
def step_bulk_delete_versions(context):
    prompt_id = getattr(context, "prompt_id", 99999)
    version_ids = getattr(context, "non_current_version_ids", [])

    from httpx import ASGITransport, AsyncClient

    cookies = {"access_token": "test-token"} if context.authenticated else {}
    files = [("version_ids", (None, str(vid))) for vid in version_ids]

    async def _do_request():
        async with AsyncClient(
            transport=ASGITransport(app=context.app),
            base_url="http://test",
            cookies=cookies,
            follow_redirects=False,
        ) as client:
            return await client.post(f"/prompts/{prompt_id}/versions/bulk-delete", files=files)

    context.response = context.loop.run_until_complete(_do_request())


# --- OpenAI configuration (shared with the knowledge base scenarios) ---


@given("OpenAI is configured")
def step_openai_configured(context):
    """Set settings.openai_api_key to a truthy value."""
    context._openai_key_needs_restore = True
    _settings.__dict__["openai_api_key"] = "test-openai-key"


@given("OpenAI is not configured")
def step_openai_not_configured(context):
    """Ensure settings.openai_api_key is empty."""
    context._openai_key_needs_restore = True
    _settings.__dict__["openai_api_key"] = ""
