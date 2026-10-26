# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Step definitions for knowledge base entry management scenarios."""

from unittest.mock import AsyncMock, MagicMock

from behave import given, when
from internal.models.knowledge import KnowledgeEntry, KnowledgeNamespace

# --- Namespace seed data ---


@given('a namespace "{slug}" with name "{name}" exists')
def step_namespace_exists(context, slug, name):
    async def _create():
        async with context.session_maker() as session:
            ns = KnowledgeNamespace(slug=slug, name=name, is_public=True)
            session.add(ns)
            await session.commit()
            await session.refresh(ns)
            context.namespace_id = ns.id
            return ns

    context.loop.run_until_complete(_create())


# --- Knowledge entry seed data ---


@given('a knowledge entry exists with question "{question}" and answer "{answer}"')
def step_knowledge_entry_exists(context, question, answer):
    async def _create():
        async with context.session_maker() as session:
            entry = KnowledgeEntry(
                question=question,
                answer=answer,
                namespace_id=getattr(context, "namespace_id", None),
                metadata_={},
            )
            session.add(entry)
            await session.commit()
            await session.refresh(entry)
            context.entry_id = entry.id
            context.created_ids.append(entry.id)
            return entry

    context.loop.run_until_complete(_create())


@given('another knowledge entry exists with question "{question}" and answer "{answer}"')
def step_another_knowledge_entry_exists(context, question, answer):
    async def _create():
        async with context.session_maker() as session:
            entry = KnowledgeEntry(
                question=question,
                answer=answer,
                namespace_id=getattr(context, "namespace_id", None),
                metadata_={},
            )
            session.add(entry)
            await session.commit()
            await session.refresh(entry)
            context.created_ids.append(entry.id)
            return entry

    context.loop.run_until_complete(_create())


# --- OpenAI configuration ---


# --- Knowledge generator mock ---


@given("the knowledge generator returns entries")
def step_knowledge_generator_returns(context):
    mock_generator = MagicMock()
    mock_generator.generate_entries = AsyncMock(
        return_value=[
            {"question": "Generated Q1", "answer": "Generated A1", "metadata": {}},
            {"question": "Generated Q2", "answer": "Generated A2", "metadata": {}},
        ]
    )
    context.mock_knowledge_generator_cls.return_value = mock_generator


@given("the generation task completed successfully")
def step_generation_task_success(context):
    """Configure the Celery AsyncResult mock to return SUCCESS state."""
    mock_result = MagicMock()
    mock_result.state = "SUCCESS"
    mock_result.result = {
        "created_count": 2,
        "entry_ids": [1, 2],
        "namespace_slug": "general",
    }
    context.mock_celery_async_result.return_value = mock_result


# --- Dynamic path request steps ---


def _make_knowledge_request(context, method, path, **kwargs):
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


def _resolve_form_data(context):
    """Parse table data and resolve placeholders like {namespace_id}."""
    data = {}
    for row in context.table:
        value = row["value"]
        if value == "{namespace_id}":
            value = str(getattr(context, "namespace_id", 1))
        data[row["field"]] = value
    return data


@when("I create a knowledge entry with form data")
def step_create_knowledge_entry(context):
    data = _resolve_form_data(context)
    _make_knowledge_request(context, "post", "/knowledge/new", data=data)


@when("I generate knowledge entries with form data")
def step_generate_knowledge(context):
    data = _resolve_form_data(context)
    _make_knowledge_request(context, "post", "/knowledge/generate", data=data)


@when("I view the knowledge entry detail")
def step_view_knowledge_detail(context):
    entry_id = getattr(context, "entry_id", 99999)
    _make_knowledge_request(context, "get", f"/knowledge/{entry_id}")


@when("I view the knowledge entry edit form")
def step_view_knowledge_edit(context):
    entry_id = getattr(context, "entry_id", 99999)
    _make_knowledge_request(context, "get", f"/knowledge/{entry_id}/edit")


@when("I update the knowledge entry with form data")
def step_update_knowledge_entry(context):
    entry_id = getattr(context, "entry_id", 99999)
    data = _resolve_form_data(context)
    _make_knowledge_request(context, "post", f"/knowledge/{entry_id}/edit", data=data)


@when("I delete the knowledge entry")
def step_delete_knowledge_entry(context):
    entry_id = getattr(context, "entry_id", 99999)
    _make_knowledge_request(context, "post", f"/knowledge/{entry_id}/delete")


@when("I bulk delete the created knowledge entries")
def step_bulk_delete_knowledge(context):
    entry_ids_str = ",".join(str(eid) for eid in context.created_ids)
    _make_knowledge_request(
        context, "post", "/knowledge/bulk-delete", data={"entry_ids": entry_ids_str}
    )
