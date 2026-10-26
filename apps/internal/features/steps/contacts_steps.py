# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Step definitions for contacts feature tests.

Uses context.mock_mailler_contacts which patches internal.routes.contacts.mailler_client.
The mailler_client returns dicts (not Pydantic models).
"""

from unittest.mock import AsyncMock

from behave import given

# ---------------------------------------------------------------------------
# Helper data factories
# ---------------------------------------------------------------------------

_EMPTY_PAGE = {"items": [], "total": 0, "page": 1, "page_size": 20, "pages": 1}


def _contacts_page(contacts=None, total=None):
    """Build a paginated contacts response dict."""
    items = contacts or []
    return {
        "items": items,
        "total": total if total is not None else len(items),
        "page": 1,
        "page_size": 50,
        "pages": 1,
    }


def _groups_page(groups=None, total=None):
    """Build a paginated groups response dict."""
    items = groups or []
    return {
        "items": items,
        "total": total if total is not None else len(items),
        "page": 1,
        "page_size": 100,
        "pages": 1,
    }


def _make_contact(**kwargs):
    """Create a sample contact dict."""
    return {
        "id": kwargs.get("id", 42),
        "email": kwargs.get("email", "test@example.com"),
        "first_name": kwargs.get("first_name", "Test"),
        "last_name": kwargs.get("last_name", "User"),
        "status": kwargs.get("status", "active"),
        "source": kwargs.get("source", "manual"),
        "groups": kwargs.get("groups", []),
        "created_at": kwargs.get("created_at", "2024-01-01T00:00:00Z"),
        "updated_at": kwargs.get("updated_at", "2024-01-01T00:00:00Z"),
    }


def _make_group(**kwargs):
    """Create a sample group dict."""
    return {
        "id": kwargs.get("id", 1),
        "name": kwargs.get("name", "Newsletter"),
        "slug": kwargs.get("slug", "newsletter"),
        "description": kwargs.get("description", "Newsletter subscribers"),
        "created_at": kwargs.get("created_at", "2024-01-01T00:00:00Z"),
        "updated_at": kwargs.get("updated_at", "2024-01-01T00:00:00Z"),
    }


# ---------------------------------------------------------------------------
# List steps
# ---------------------------------------------------------------------------


@given("the contacts list returns data")
def step_contacts_list(context):
    mock = context.mock_mailler_contacts
    mock.get_contacts = AsyncMock(return_value=_contacts_page([_make_contact()]))
    mock.get_contact_groups = AsyncMock(return_value=_groups_page([_make_group()]))


@given("the contact groups list returns data")
def step_contact_groups_list(context):
    mock = context.mock_mailler_contacts
    mock.get_contact_groups = AsyncMock(return_value=_groups_page([_make_group()]))


@given("the contacts list returns data for export")
def step_contacts_list_export(context):
    mock = context.mock_mailler_contacts
    mock.get_contacts = AsyncMock(return_value=_contacts_page([_make_contact()], total=1))


# ---------------------------------------------------------------------------
# Detail steps
# ---------------------------------------------------------------------------


@given('a contact exists with id "{contact_id}"')
def step_contact_exists(context, contact_id):
    mock = context.mock_mailler_contacts
    contact = _make_contact(id=int(contact_id))
    mock.get_contact = AsyncMock(return_value=contact)
    # Also set up groups for edit form
    if not isinstance(getattr(mock, "get_contact_groups", None), AsyncMock):
        mock.get_contact_groups = AsyncMock(return_value=_groups_page([_make_group()]))


@given("a contact does not exist")
def step_contact_not_exists(context):
    mock = context.mock_mailler_contacts
    mock.get_contact = AsyncMock(return_value=None)


# ---------------------------------------------------------------------------
# Create steps
# ---------------------------------------------------------------------------


@given("creating a contact succeeds")
def step_create_contact_succeeds(context):
    mock = context.mock_mailler_contacts
    mock.create_contact = AsyncMock(return_value=_make_contact(id=99))
    mock.add_contacts_to_group = AsyncMock(return_value={"added": 1})


@given("creating a contact fails")
def step_create_contact_fails(context):
    mock = context.mock_mailler_contacts
    mock.create_contact = AsyncMock(return_value=None)


# ---------------------------------------------------------------------------
# Update steps
# ---------------------------------------------------------------------------


@given('updating a contact succeeds for id "{contact_id}"')
def step_update_contact_succeeds(context, contact_id):
    mock = context.mock_mailler_contacts
    contact = _make_contact(id=int(contact_id), groups=[])
    mock.get_contact = AsyncMock(return_value=contact)
    mock.update_contact = AsyncMock(return_value=contact)
    mock.add_contacts_to_group = AsyncMock(return_value={"added": 0})
    mock.remove_contacts_from_group = AsyncMock(return_value={"removed": 0})


@given('updating a contact fails for id "{contact_id}"')
def step_update_contact_fails(context, contact_id):
    mock = context.mock_mailler_contacts
    contact = _make_contact(id=int(contact_id), groups=[])
    mock.get_contact = AsyncMock(return_value=contact)
    mock.update_contact = AsyncMock(return_value=None)


# ---------------------------------------------------------------------------
# Unsubscribe steps
# ---------------------------------------------------------------------------


@given('unsubscribing a contact succeeds for id "{contact_id}"')
def step_unsubscribe_succeeds(context, contact_id):
    mock = context.mock_mailler_contacts
    mock.unsubscribe_contact = AsyncMock(
        return_value=_make_contact(id=int(contact_id), status="unsubscribed")
    )


@given('unsubscribing a contact fails for id "{contact_id}"')
def step_unsubscribe_fails(context, contact_id):
    mock = context.mock_mailler_contacts
    mock.unsubscribe_contact = AsyncMock(return_value=None)


# ---------------------------------------------------------------------------
# Delete steps
# ---------------------------------------------------------------------------


@given('deleting a contact succeeds for id "{contact_id}"')
def step_delete_contact_succeeds(context, contact_id):
    mock = context.mock_mailler_contacts
    mock.delete_contact = AsyncMock(return_value=True)


@given('deleting a contact fails for id "{contact_id}"')
def step_delete_contact_fails(context, contact_id):
    mock = context.mock_mailler_contacts
    mock.delete_contact = AsyncMock(return_value=False)


# ---------------------------------------------------------------------------
# Bulk operation steps
# ---------------------------------------------------------------------------


@given("bulk deleting contacts succeeds")
def step_bulk_delete_succeeds(context):
    mock = context.mock_mailler_contacts
    mock.delete_contact = AsyncMock(return_value=True)


@given("bulk adding contacts to group succeeds")
def step_bulk_add_to_group_succeeds(context):
    mock = context.mock_mailler_contacts
    mock.add_contacts_to_group = AsyncMock(return_value={"added": 3})
