# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Steps that prepare workspaces, collections and documents for the ``@browser`` scenarios.

The data is written to the SQLite stand-in of the scenario, with the people of the identity
provider as members; the pages then read it like they read the real database.
"""

import hashlib
import re
from uuid import UUID

import browser_stack
from behave import given
from browser_steps import email_of
from fakes import hashing_vectorizer

from knowledge.config import get_settings
from knowledge.models import Collection, Document, Organization, OrganizationMember
from knowledge.models.enums import OrganizationMemberRole, OwnerType, PlanType


def _slug(text):
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def _join(context, name, workspace, plan, role):
    user_id = UUID(browser_stack.persona_id(email_of(name)))
    with context.stack.db.session() as session:
        organization = (
            session.query(Organization).filter(Organization.name == workspace).one_or_none()
        )
        if organization is None:
            organization = Organization(
                name=workspace,
                slug=_slug(workspace),
                plan=PlanType(plan),
                is_active=True,
            )
            session.add(organization)
            session.flush()
        session.add(
            OrganizationMember(
                organization_id=organization.id,
                user_id=user_id,
                role=OrganizationMemberRole(role),
                email=email_of(name),
                display_name=name,
            )
        )


@given('"{name}" owns the workspace "{workspace}" on the "{plan}" plan')
def step_owner(context, name, workspace, plan):
    _join(context, name, workspace, plan, "owner")


@given('"{name}" administers the workspace "{workspace}" on the "{plan}" plan')
def step_administrator(context, name, workspace, plan):
    _join(context, name, workspace, plan, "admin")


@given('"{name}" is a member of the workspace "{workspace}" on the "{plan}" plan')
def step_member(context, name, workspace, plan):
    _join(context, name, workspace, plan, "member")


@given('the workspace "{workspace}" contains the collection "{name}"')
def step_collection(context, workspace, name):
    with context.stack.db.session() as session:
        organization = session.query(Organization).filter(Organization.name == workspace).one()
        session.add(
            Collection(
                owner_type=OwnerType.ORGANIZATION,
                owner_id=organization.id,
                organization_id=organization.id,
                name=name,
                slug=_slug(name),
            )
        )


@given('the collection "{name}" contains the document "{content}"')
def step_document(context, name, content):
    vector = hashing_vectorizer(content, get_settings().embedding_dimension)
    with context.stack.db.session() as session:
        collection = session.query(Collection).filter(Collection.name == name).one()
        session.add(
            Document(
                collection_id=collection.id,
                content=content,
                embedding=vector,
                content_hash=hashlib.sha256(content.encode()).hexdigest(),
                content_size=len(content.encode()),
                embedding_size=len(vector) * 4,
            )
        )
        collection.document_count += 1
