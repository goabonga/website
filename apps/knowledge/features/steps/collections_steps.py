# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Steps for the collections feature."""

from unittest.mock import patch

from behave import given, when
from fakes import FakeAccessService, FakeCollectionService

from knowledge.models.enums import OwnerType
from knowledge.schemas.collection import CollectionCreate


@given("the collections data layer is in memory")
def step_collections_in_memory(context):
    store = context.store
    for target, fake in (
        ("knowledge.routes.collections.CollectionService", FakeCollectionService),
        ("knowledge.routes.collections.CollectionAccessService", FakeAccessService),
    ):
        patcher = patch(target, lambda db, fake=fake: fake(store))
        patcher.start()
        context.add_cleanup(patcher.stop)


@given('a collection "{name}" with slug "{slug}"')
def step_existing_collection(context, name, slug):
    import asyncio
    from uuid import UUID

    service = FakeCollectionService(context.store)
    asyncio.run(
        service.create_for_owner(
            OwnerType.USER, UUID(context.user_id), CollectionCreate(name=name, slug=slug)
        )
    )


def _collection_id(context, slug):
    for collection in context.store.collections.values():
        if collection.slug == slug:
            return collection.id
    raise AssertionError(f"no collection with slug {slug}")


@when('I update the collection "{slug}" with JSON')
def step_update_collection(context, slug):
    import json

    context.response = context.call(
        "PATCH",
        f"/api/v1/collections/{_collection_id(context, slug)}",
        json=json.loads(context.text),
    )


@when('I delete the collection "{slug}"')
def step_delete_collection(context, slug):
    context.response = context.call(
        "DELETE", f"/api/v1/collections/{_collection_id(context, slug)}"
    )
