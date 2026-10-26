# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Steps for the browser scenarios of the contact management."""

from unittest.mock import AsyncMock

from behave import given, then


@given("the contacts list has {pages:d} pages")
def step_contacts_pages(context, pages):
    contact = {
        "id": 42,
        "email": "test@example.com",
        "first_name": "Test",
        "last_name": "User",
        "status": "active",
        "source": "manual",
        "groups": [],
        "created_at": "2024-01-01T00:00:00Z",
        "updated_at": "2024-01-01T00:00:00Z",
    }
    context.mock_mailler_contacts.get_contacts = AsyncMock(
        return_value={
            "items": [contact],
            "total": pages * 50,
            "page": 1,
            "page_size": 50,
            "pages": pages,
        }
    )


@given("the mailler service imports contacts")
def step_import_contacts(context):
    context.mock_mailler_contacts.create_contacts_bulk = AsyncMock(
        return_value={"created": 2, "skipped": 1, "failed": 0}
    )


@then("the contacts should have been imported")
def step_contacts_imported(context):
    kwargs = context.mock_mailler_contacts.create_contacts_bulk.await_args.kwargs
    emails = [contact["email"] for contact in kwargs["contacts"]]
    assert emails == ["ada@example.com", "grace@example.com"], emails


@then('the mailler service should have been asked for the contacts matching "{text}"')
def step_contacts_matching(context, text):
    kwargs = context.mock_mailler_contacts.get_contacts.await_args.kwargs
    assert kwargs["search"] == text, kwargs


@then('the mailler service should have been asked to delete the contacts "{ids}"')
def step_contacts_deleted(context, ids):
    deleted = sorted(
        str(call.args[0]) for call in context.mock_mailler_contacts.delete_contact.await_args_list
    )
    assert deleted == sorted(ids.split(",")), deleted


@then('the contact "{contact_id}" should have been added to the group "{group_id}"')
def step_contact_added(context, contact_id, group_id):
    calls = context.mock_mailler_contacts.add_contacts_to_group.await_args_list
    assert any(
        str(call.args[0]) == group_id and contact_id in [str(c) for c in call.args[1]]
        for call in calls
    ), calls


@then("the mailler service should not have updated the contact")
def step_no_contact_updated(context):
    context.mock_mailler_contacts.update_contact.assert_not_awaited()


@then("the mailler service should not have deleted a contact")
def step_no_contact_deleted(context):
    context.mock_mailler_contacts.delete_contact.assert_not_awaited()


@then("the mailler service should not have been asked to create a contact")
def step_no_contact_created(context):
    context.mock_mailler_contacts.create_contact.assert_not_awaited()
