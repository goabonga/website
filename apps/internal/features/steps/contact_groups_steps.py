# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Step definitions for contact groups feature tests.

Uses context.mock_mailler_groups which patches internal.routes.contact_groups.mailler_client.
The mailler_client returns dicts (not Pydantic models).
"""

from unittest.mock import AsyncMock

from behave import given

# ---------------------------------------------------------------------------
# Helper data factories
# ---------------------------------------------------------------------------


def _groups_page(groups=None, total=None):
    """Build a paginated groups response dict."""
    items = groups or []
    return {
        "items": items,
        "total": total if total is not None else len(items),
        "page": 1,
        "page_size": 20,
        "pages": 1,
    }


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


def _make_group(**kwargs):
    """Create a sample group dict."""
    return {
        "id": kwargs.get("id", 1),
        "name": kwargs.get("name", "Newsletter"),
        "slug": kwargs.get("slug", "newsletter"),
        "description": kwargs.get("description", "Newsletter subscribers"),
        "member_count": kwargs.get("member_count", 5),
        "is_dynamic": kwargs.get("is_dynamic", False),
        "created_at": kwargs.get("created_at", "2024-01-01T00:00:00Z"),
        "updated_at": kwargs.get("updated_at", "2024-01-01T00:00:00Z"),
    }


def _make_contact(**kwargs):
    """Create a sample contact dict."""
    first_name = kwargs.get("first_name", "Test")
    last_name = kwargs.get("last_name", "User")
    return {
        "id": kwargs.get("id", 1),
        "email": kwargs.get("email", "test@example.com"),
        "first_name": first_name,
        "last_name": last_name,
        "full_name": kwargs.get("full_name", f"{first_name} {last_name}"),
        "status": kwargs.get("status", "active"),
        "source": kwargs.get("source", "manual"),
        "groups": kwargs.get("groups", []),
        "created_at": kwargs.get("created_at", "2024-01-01T00:00:00Z"),
        "updated_at": kwargs.get("updated_at", "2024-01-01T00:00:00Z"),
    }


# ---------------------------------------------------------------------------
# List steps
# ---------------------------------------------------------------------------


@given("the contact groups list returns groups")
def step_groups_list(context):
    mock = context.mock_mailler_groups
    mock.get_contact_groups = AsyncMock(return_value=_groups_page([_make_group()]))


# ---------------------------------------------------------------------------
# Detail / existence steps
# ---------------------------------------------------------------------------


@given('a contact group exists with id "{group_id}"')
def step_group_exists(context, group_id):
    mock = context.mock_mailler_groups
    group = _make_group(id=int(group_id))
    mock.get_contact_group = AsyncMock(return_value=group)
    # Always set up members for detail view
    mock.get_group_contacts = AsyncMock(return_value=_contacts_page([_make_contact()]))


@given("a contact group does not exist")
def step_group_not_exists(context):
    mock = context.mock_mailler_groups
    mock.get_contact_group = AsyncMock(return_value=None)


# ---------------------------------------------------------------------------
# Create steps
# ---------------------------------------------------------------------------


@given("creating a contact group succeeds")
def step_create_group_succeeds(context):
    mock = context.mock_mailler_groups
    mock.create_contact_group = AsyncMock(
        return_value=_make_group(id=10, name="VIP Customers", slug="vip-customers")
    )


@given("creating a contact group fails")
def step_create_group_fails(context):
    mock = context.mock_mailler_groups
    mock.create_contact_group = AsyncMock(return_value=None)


# ---------------------------------------------------------------------------
# Update steps
# ---------------------------------------------------------------------------


@given('updating a contact group succeeds for id "{group_id}"')
def step_update_group_succeeds(context, group_id):
    mock = context.mock_mailler_groups
    group = _make_group(id=int(group_id))
    mock.get_contact_group = AsyncMock(return_value=group)
    mock.update_contact_group = AsyncMock(
        return_value=_make_group(id=int(group_id), name="Updated Group")
    )


@given('updating a contact group fails for id "{group_id}"')
def step_update_group_fails(context, group_id):
    mock = context.mock_mailler_groups
    group = _make_group(id=int(group_id))
    mock.get_contact_group = AsyncMock(return_value=group)
    mock.update_contact_group = AsyncMock(return_value=None)


# ---------------------------------------------------------------------------
# Add / remove contacts steps
# ---------------------------------------------------------------------------


@given('contacts not in group "{group_id}" returns data')
def step_contacts_not_in_group(context, group_id):
    mock = context.mock_mailler_groups
    mock.get_contacts_not_in_group = AsyncMock(
        return_value=_contacts_page([_make_contact(id=10), _make_contact(id=11)])
    )


@given('adding contacts to group "{group_id}" succeeds')
def step_add_contacts_to_group_succeeds(context, group_id):
    mock = context.mock_mailler_groups
    mock.add_contacts_to_group = AsyncMock(return_value={"added": 3})


@given('removing contacts from group "{group_id}" succeeds')
def step_remove_contacts_from_group_succeeds(context, group_id):
    mock = context.mock_mailler_groups
    mock.remove_contacts_from_group = AsyncMock(return_value={"removed": 2})


# ---------------------------------------------------------------------------
# Delete steps
# ---------------------------------------------------------------------------


@given('deleting contact group "{group_id}" succeeds')
def step_delete_group_succeeds(context, group_id):
    mock = context.mock_mailler_groups
    mock.delete_contact_group = AsyncMock(return_value=True)


@given("bulk deleting contact groups succeeds")
def step_bulk_delete_groups_succeeds(context):
    mock = context.mock_mailler_groups
    mock.delete_contact_group = AsyncMock(return_value=True)
