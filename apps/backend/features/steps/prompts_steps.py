# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Step definitions for the system prompts feature."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from backend.models.prompt import SystemPrompt, SystemPromptVersion
from backend.prompts.service import DEFAULT_FALLBACK_PROMPT, PromptService
from behave import given, then, when


def _scopes(text):
    return {scope.strip() for scope in text.split(",") if scope.strip()}


def _set_prompts(context, prompts):
    result = MagicMock()
    result.scalars.return_value.all.return_value = prompts
    context.db.execute.return_value = result


@given("the prompt cache is empty")
def step_empty_cache(context):
    patcher = patch("backend.prompts.service.prompt_cache")
    cache = patcher.start()
    context.patches["prompt_cache"] = patcher
    cache.get_for_scopes = AsyncMock(return_value=None)
    cache.set_for_scopes = AsyncMock()
    context.cache = cache


@given("the database holds the prompts:")
def step_prompts(context):
    prompts = []
    for index, row in enumerate(context.table, start=1):
        scopes = sorted(_scopes(row["scopes"])) or None
        prompt = SystemPrompt(
            id=index,
            slug=row["slug"],
            name=row["slug"],
            is_default=row["default"] == "yes",
            required_scopes=scopes,
        )
        prompt.versions = [
            SystemPromptVersion(
                id=index, prompt_id=index, version=1, content=row["content"], is_current=True
            )
        ]
        prompts.append(prompt)
    _set_prompts(context, prompts)


@given("the database holds no prompt")
def step_no_prompts(context):
    _set_prompts(context, [])


@given('the cache already holds "{content}" for every caller')
def step_cache_hit(context, content):
    context.cache.get_for_scopes.return_value = content


def _request(context, scopes):
    service = PromptService(context.db)
    context.prompt = asyncio.run(service.get_prompt_for_scopes(scopes))


@when("the prompt is requested for an anonymous user")
def step_anonymous(context):
    _request(context, None)


@when('the prompt is requested for the scopes "{scopes}"')
def step_scopes(context, scopes):
    context.requested_scopes = _scopes(scopes)
    _request(context, context.requested_scopes)


@then('the prompt should be "{content}"')
def step_prompt(context, content):
    assert context.prompt == content, context.prompt


@then("the prompt should be the built-in fallback")
def step_fallback(context):
    assert context.prompt == DEFAULT_FALLBACK_PROMPT


@then('the scope cache should hold "{content}"')
def step_cached(context, content):
    context.cache.set_for_scopes.assert_awaited_once_with(context.requested_scopes, content)


@then("the database should not have been queried")
def step_no_query(context):
    context.db.execute.assert_not_awaited()
