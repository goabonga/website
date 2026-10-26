# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Step definitions for knowledge namespace management scenarios."""

from behave import given, when
from internal.models.knowledge import KnowledgeNamespace

# --- Namespace seed data (namespaces-specific to avoid step collisions with knowledge_steps) ---


@given('a namespace "{slug}" with name "{name}" exists for namespaces')
def step_ns_namespace_exists(context, slug, name):
    async def _create():
        async with context.session_maker() as session:
            ns = KnowledgeNamespace(slug=slug, name=name, is_public=True)
            session.add(ns)
            await session.commit()
            await session.refresh(ns)
            context.ns_namespace_id = ns.id
            context.created_ids.append(ns.id)
            return ns

    context.loop.run_until_complete(_create())


@given('another namespace "{slug}" with name "{name}" exists for namespaces')
def step_ns_another_namespace_exists(context, slug, name):
    async def _create():
        async with context.session_maker() as session:
            ns = KnowledgeNamespace(slug=slug, name=name, is_public=True)
            session.add(ns)
            await session.commit()
            await session.refresh(ns)
            context.created_ids.append(ns.id)
            return ns

    context.loop.run_until_complete(_create())


@given("the default general namespace exists")
def step_default_general_namespace(context):
    async def _create():
        async with context.session_maker() as session:
            ns = KnowledgeNamespace(
                slug="general",
                name="General",
                description="Default namespace for general knowledge entries",
                is_public=True,
            )
            session.add(ns)
            await session.commit()
            await session.refresh(ns)
            context.ns_namespace_id = ns.id
            return ns

    context.loop.run_until_complete(_create())


# --- Helper ---


def _make_ns_request(context, method, path, **kwargs):
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


# --- Dynamic path request steps ---


@when("I view the namespace detail")
def step_view_namespace_detail(context):
    namespace_id = getattr(context, "ns_namespace_id", 99999)
    _make_ns_request(context, "get", f"/namespaces/{namespace_id}")


@when("I view the namespace edit form")
def step_view_namespace_edit(context):
    namespace_id = getattr(context, "ns_namespace_id", 99999)
    _make_ns_request(context, "get", f"/namespaces/{namespace_id}/edit")


@when("I update the namespace with form data")
def step_update_namespace(context):
    namespace_id = getattr(context, "ns_namespace_id", 99999)
    data = {}
    for row in context.table:
        data[row["field"]] = row["value"]
    _make_ns_request(context, "post", f"/namespaces/{namespace_id}/edit", data=data)


@when("I delete the namespace")
def step_delete_namespace(context):
    namespace_id = getattr(context, "ns_namespace_id", 99999)
    _make_ns_request(context, "post", f"/namespaces/{namespace_id}/delete")


@when("I bulk delete the created namespaces")
def step_bulk_delete_namespaces(context):
    from httpx import ASGITransport, AsyncClient

    cookies = {"access_token": "test-token"} if context.authenticated else {}
    files = [("namespace_ids", (None, str(nid))) for nid in context.created_ids]

    async def _do_request():
        async with AsyncClient(
            transport=ASGITransport(app=context.app),
            base_url="http://test",
            cookies=cookies,
            follow_redirects=False,
        ) as client:
            return await client.post("/namespaces/bulk-delete", files=files)

    context.response = context.loop.run_until_complete(_do_request())
