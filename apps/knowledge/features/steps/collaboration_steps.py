# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Steps for the collaborators and invitations feature."""

import asyncio
from datetime import UTC, datetime
from unittest.mock import patch
from uuid import UUID, uuid4

from behave import given, then, when
from fakes import (
    FakeAccessService,
    FakeCollaboratorService,
    FakeCollectionService,
    FakeInvitationService,
)

from knowledge.models import Collection
from knowledge.models.enums import CollaboratorPermission, OwnerType

BASE = "/api/v1/collections"


@given("the collaboration data layer is in memory")
def step_collaboration_in_memory(context):
    store = context.store
    for target, fake in (
        (
            "knowledge.routes.collaborators.CollectionService",
            lambda db: FakeCollectionService(store),
        ),
        (
            "knowledge.routes.collaborators.CollectionAccessService",
            lambda db: FakeAccessService(store),
        ),
        ("knowledge.routes.collaborators.CollaboratorService", FakeCollaboratorService),
        (
            "knowledge.routes.collection_invitations.CollectionService",
            lambda db: FakeCollectionService(store),
        ),
        (
            "knowledge.routes.collection_invitations.CollectionAccessService",
            lambda db: FakeAccessService(store),
        ),
        (
            "knowledge.routes.collection_invitations.CollectionInvitationService",
            FakeInvitationService,
        ),
        ("knowledge.services.collaborators.CollaboratorService", FakeCollaboratorService),
    ):
        patcher = patch(target, fake)
        patcher.start()
        context.add_cleanup(patcher.stop)


@given('I own a collection "{name}" with slug "{slug}"')
def step_own_collection(context, name, slug):
    now = datetime.now(UTC)
    collection = Collection(
        id=uuid4(),
        owner_type=OwnerType.USER,
        owner_id=UUID(context.user_id),
        name=name,
        slug=slug,
        embedding_model="text-embedding-3-small",
        dimension=1536,
        document_count=0,
        created_at=now,
        updated_at=now,
    )
    context.store.collections[collection.id] = collection
    context.owner_id = context.user_id


def _collection_id(context, slug):
    return next(c.id for c in context.store.collections.values() if c.slug == slug)


def _invitation(context, email):
    return next(i for i in context.store.invitations.values() if i.email == email.lower())


def _run(coro):
    return asyncio.run(coro)


@given('user "{user_id}" is a "{permission}" collaborator of "{slug}"')
def step_existing_collaborator(context, user_id, permission, slug):
    service = FakeCollaboratorService(context.session)
    _run(
        service.add(
            _collection_id(context, slug),
            UUID(user_id),
            CollaboratorPermission(permission),
            UUID(context.owner_id),
        )
    )


@given('"{email}" is invited to "{slug}" with permission "{permission}"')
def step_existing_invitation(context, email, slug, permission):
    service = FakeInvitationService(context.session)
    _run(
        service.create(
            _collection_id(context, slug),
            email,
            CollaboratorPermission(permission),
            UUID(context.owner_id),
        )
    )


@when('I add user "{user_id}" as "{permission}" collaborator of "{slug}"')
def step_add_collaborator(context, user_id, permission, slug):
    context.response = context.call(
        "POST",
        f"{BASE}/{_collection_id(context, slug)}/collaborators",
        json={"user_id": user_id, "permission": permission},
    )


@when('I list the collaborators of "{slug}"')
def step_list_collaborators(context, slug):
    context.response = context.call("GET", f"{BASE}/{_collection_id(context, slug)}/collaborators")


@when('I change the permission of user "{user_id}" on "{slug}" to "{permission}"')
def step_change_permission(context, user_id, slug, permission):
    context.response = context.call(
        "PATCH",
        f"{BASE}/{_collection_id(context, slug)}/collaborators/{user_id}",
        json={"permission": permission},
    )


@when('I remove user "{user_id}" from "{slug}"')
def step_remove_collaborator(context, user_id, slug):
    context.response = context.call(
        "DELETE", f"{BASE}/{_collection_id(context, slug)}/collaborators/{user_id}"
    )


@when('I invite "{email}" to "{slug}" with permission "{permission}"')
def step_invite(context, email, slug, permission):
    context.response = context.call(
        "POST",
        f"{BASE}/{_collection_id(context, slug)}/invitations",
        json={"email": email, "permission": permission},
    )


@when('I list the invitations of "{slug}"')
def step_list_invitations(context, slug):
    context.response = context.call("GET", f"{BASE}/{_collection_id(context, slug)}/invitations")


@when('I view the invitation of "{email}"')
def step_view_invitation(context, email):
    context.response = context.call(
        "GET", f"/api/v1/collection-invites/{_invitation(context, email).token}"
    )


@when('I accept the invitation of "{email}"')
def step_accept_invitation(context, email):
    context.response = context.call(
        "POST", f"/api/v1/collection-invites/{_invitation(context, email).token}/accept"
    )


@when('I revoke the invitation of "{email}" on "{slug}"')
def step_revoke_invitation(context, email, slug):
    invitation = _invitation(context, email)
    context.response = context.call(
        "DELETE", f"{BASE}/{_collection_id(context, slug)}/invitations/{invitation.id}"
    )


@when('I resend the invitation of "{email}" on "{slug}"')
def step_resend_invitation(context, email, slug):
    invitation = _invitation(context, email)
    context.previous_token = invitation.token
    context.response = context.call(
        "POST", f"{BASE}/{_collection_id(context, slug)}/invitations/{invitation.id}/resend"
    )


@then('the invitation of "{email}" should have a new token')
def step_new_token(context, email):
    assert _invitation(context, email).token != context.previous_token


@then('user "{user_id}" should be a collaborator of "{slug}"')
def step_is_collaborator(context, user_id, slug):
    collection_id = _collection_id(context, slug)
    assert any(
        c.collection_id == collection_id and c.user_id == UUID(user_id)
        for c in context.store.collaborators.values()
    )
