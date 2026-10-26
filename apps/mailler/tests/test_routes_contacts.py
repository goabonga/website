# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for contact CRUD routes."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from httpx import AsyncClient
from sqlalchemy.exc import IntegrityError


def _make_db_list_response(items=None, total=0):
    count_result = MagicMock()
    count_result.scalar.return_value = total
    list_result = MagicMock()
    list_result.scalars.return_value.all.return_value = items or []
    return [count_result, list_result]


def _make_contact_mock(**overrides):
    now = datetime.now(UTC)
    c = MagicMock()
    c.id = overrides.get("id", uuid4())
    c.client_id = overrides.get("client_id", "test-client-id")
    c.email = overrides.get("email", "test@example.com")
    c.first_name = overrides.get("first_name", "Test")
    c.last_name = overrides.get("last_name", "User")
    c.full_name = overrides.get("full_name", "Test User")
    c.status = overrides.get("status", "active")
    c.source = overrides.get("source", "api")
    c.custom_fields = overrides.get("custom_fields", {})
    c.created_at = overrides.get("created_at", now)
    c.updated_at = overrides.get("updated_at", now)
    c.group_memberships = overrides.get("group_memberships", [])
    return c


# --------------------------------------------------------------------------
# GET /contacts
# --------------------------------------------------------------------------


class TestListContacts:
    async def test_list_empty(self, auth_client: AsyncClient, mock_db_session):
        mock_db_session.execute = AsyncMock(side_effect=_make_db_list_response(items=[], total=0))
        response = await auth_client.get("/api/v1/contacts")
        assert response.status_code == 200
        assert response.json()["items"] == []

    async def test_list_with_items(self, auth_client: AsyncClient, mock_db_session):
        contact = _make_contact_mock()
        mock_db_session.execute = AsyncMock(
            side_effect=_make_db_list_response(items=[contact], total=1)
        )
        response = await auth_client.get("/api/v1/contacts")
        assert response.status_code == 200
        assert len(response.json()["items"]) == 1

    async def test_list_with_status_filter(self, auth_client: AsyncClient, mock_db_session):
        mock_db_session.execute = AsyncMock(side_effect=_make_db_list_response(items=[], total=0))
        response = await auth_client.get("/api/v1/contacts?status=active")
        assert response.status_code == 200

    async def test_list_with_search(self, auth_client: AsyncClient, mock_db_session):
        mock_db_session.execute = AsyncMock(side_effect=_make_db_list_response(items=[], total=0))
        response = await auth_client.get("/api/v1/contacts?search=test")
        assert response.status_code == 200

    async def test_list_with_group_filter(self, auth_client: AsyncClient, mock_db_session):
        mock_db_session.execute = AsyncMock(side_effect=_make_db_list_response(items=[], total=0))
        response = await auth_client.get("/api/v1/contacts?group_id=1")
        assert response.status_code == 200


# --------------------------------------------------------------------------
# POST /contacts
# --------------------------------------------------------------------------


class TestCreateContact:
    async def test_create_success(self, admin_client: AsyncClient, mock_db_session):
        response = await admin_client.post(
            "/api/v1/contacts",
            json={"email": "new@example.com", "first_name": "New", "last_name": "C"},
        )
        assert response.status_code == 201
        data = response.json()
        assert data["email"] == "new@example.com"
        assert data["status"] == "active"

    async def test_create_duplicate_email(self, admin_client: AsyncClient, mock_db_session):
        mock_db_session.commit = AsyncMock(side_effect=IntegrityError("", {}, Exception()))
        response = await admin_client.post(
            "/api/v1/contacts",
            json={"email": "dup@example.com"},
        )
        assert response.status_code == 409


# --------------------------------------------------------------------------
# POST /contacts/bulk
# --------------------------------------------------------------------------


class TestBulkCreateContacts:
    @patch("mailler.routes.contacts.logger")
    async def test_bulk_create_success(
        self, mock_logger, admin_client: AsyncClient, mock_db_session
    ):
        # No existing contacts found
        result = MagicMock()
        result.scalar_one_or_none.return_value = None
        mock_db_session.execute = AsyncMock(return_value=result)

        response = await admin_client.post(
            "/api/v1/contacts/bulk",
            json={
                "contacts": [
                    {"email": "a@t.com", "first_name": "A"},
                    {"email": "b@t.com", "first_name": "B"},
                ],
                "skip_existing": True,
            },
        )
        assert response.status_code == 201
        data = response.json()
        assert data["created"] == 2
        assert data["skipped"] == 0

    @patch("mailler.routes.contacts.logger")
    async def test_bulk_skip_existing(
        self, mock_logger, admin_client: AsyncClient, mock_db_session
    ):
        existing = MagicMock()
        result = MagicMock()
        result.scalar_one_or_none.return_value = existing
        mock_db_session.execute = AsyncMock(return_value=result)

        response = await admin_client.post(
            "/api/v1/contacts/bulk",
            json={
                "contacts": [{"email": "exists@t.com"}],
                "skip_existing": True,
            },
        )
        assert response.status_code == 201
        assert response.json()["skipped"] == 1

    @patch("mailler.routes.contacts.logger")
    async def test_bulk_fail_existing(
        self, mock_logger, admin_client: AsyncClient, mock_db_session
    ):
        existing = MagicMock()
        result = MagicMock()
        result.scalar_one_or_none.return_value = existing
        mock_db_session.execute = AsyncMock(return_value=result)

        response = await admin_client.post(
            "/api/v1/contacts/bulk",
            json={
                "contacts": [{"email": "exists@t.com"}],
                "skip_existing": False,
            },
        )
        assert response.status_code == 201
        data = response.json()
        assert data["failed"] == 1
        assert data["errors"] is not None

    @patch("mailler.routes.contacts.logger")
    async def test_bulk_create_generic_exception(
        self, mock_logger, admin_client: AsyncClient, mock_db_session
    ):
        """Cover lines 230-232: generic Exception during bulk contact processing."""
        mock_db_session.execute = AsyncMock(side_effect=RuntimeError("unexpected db error"))

        response = await admin_client.post(
            "/api/v1/contacts/bulk",
            json={
                "contacts": [{"email": "fail@t.com"}],
                "skip_existing": True,
            },
        )
        assert response.status_code == 201
        data = response.json()
        assert data["failed"] == 1
        assert data["created"] == 0
        assert data["errors"] is not None
        assert "fail@t.com" in data["errors"][0]


# --------------------------------------------------------------------------
# GET /contacts/{id}
# --------------------------------------------------------------------------


class TestGetContact:
    async def test_get_found(self, auth_client: AsyncClient, mock_db_session):
        contact_id = uuid4()
        contact = _make_contact_mock(id=contact_id)
        result = MagicMock()
        result.scalar_one_or_none.return_value = contact
        mock_db_session.execute = AsyncMock(return_value=result)

        response = await auth_client.get(f"/api/v1/contacts/{contact_id}")
        assert response.status_code == 200
        assert response.json()["id"] == str(contact_id)

    async def test_get_not_found(self, auth_client: AsyncClient, mock_db_session):
        result = MagicMock()
        result.scalar_one_or_none.return_value = None
        mock_db_session.execute = AsyncMock(return_value=result)
        response = await auth_client.get(f"/api/v1/contacts/{uuid4()}")
        assert response.status_code == 404

    async def test_get_with_groups(self, auth_client: AsyncClient, mock_db_session):
        contact_id = uuid4()
        grp = MagicMock()
        grp.id = 1
        grp.slug = "grp"
        grp.name = "Group"
        membership = MagicMock()
        membership.group = grp
        contact = _make_contact_mock(id=contact_id, group_memberships=[membership])

        result = MagicMock()
        result.scalar_one_or_none.return_value = contact
        mock_db_session.execute = AsyncMock(return_value=result)

        response = await auth_client.get(f"/api/v1/contacts/{contact_id}")
        assert response.status_code == 200
        assert len(response.json()["groups"]) == 1


# --------------------------------------------------------------------------
# GET /contacts/by-email/{email}
# --------------------------------------------------------------------------


class TestGetContactByEmail:
    async def test_found(self, auth_client: AsyncClient, mock_db_session):
        contact = _make_contact_mock()
        result = MagicMock()
        result.scalar_one_or_none.return_value = contact
        mock_db_session.execute = AsyncMock(return_value=result)

        response = await auth_client.get("/api/v1/contacts/by-email/test@example.com")
        assert response.status_code == 200

    async def test_not_found(self, auth_client: AsyncClient, mock_db_session):
        result = MagicMock()
        result.scalar_one_or_none.return_value = None
        mock_db_session.execute = AsyncMock(return_value=result)

        response = await auth_client.get("/api/v1/contacts/by-email/nope@example.com")
        assert response.status_code == 404


# --------------------------------------------------------------------------
# PUT /contacts/{id}
# --------------------------------------------------------------------------


class TestUpdateContact:
    async def test_update_success(self, admin_client: AsyncClient, mock_db_session):
        contact_id = uuid4()
        contact = _make_contact_mock(id=contact_id)
        mock_db_session.get = AsyncMock(return_value=contact)

        # After commit, route reloads via execute
        reloaded = _make_contact_mock(id=contact_id, first_name="Updated")
        reload_result = MagicMock()
        reload_result.scalar_one_or_none.return_value = None  # scalar_one
        reload_result.scalar_one.return_value = reloaded
        mock_db_session.execute = AsyncMock(return_value=reload_result)

        response = await admin_client.put(
            f"/api/v1/contacts/{contact_id}",
            json={
                "first_name": "Updated",
                "last_name": "Name",
                "source": "web",
                "custom_fields": {"k": "v"},
            },
        )
        assert response.status_code == 200

    async def test_update_not_found(self, admin_client: AsyncClient, mock_db_session):
        mock_db_session.get = AsyncMock(return_value=None)
        response = await admin_client.put(f"/api/v1/contacts/{uuid4()}", json={"first_name": "X"})
        assert response.status_code == 404

    async def test_update_status_change_brevo_unblock(
        self, admin_client: AsyncClient, mock_db_session
    ):
        contact_id = uuid4()
        contact = _make_contact_mock(id=contact_id, status="bounced", email="bounced@t.com")
        mock_db_session.get = AsyncMock(return_value=contact)

        reloaded = _make_contact_mock(id=contact_id, status="active")
        reload_result = MagicMock()
        reload_result.scalar_one.return_value = reloaded
        mock_db_session.execute = AsyncMock(return_value=reload_result)

        with patch("mailler.services.providers.brevo.BrevoProvider") as MockBrevo:
            mock_brevo = MagicMock()
            mock_brevo.is_configured = True
            mock_brevo.unblock_contact = AsyncMock(return_value={"success": True, "message": "ok"})
            MockBrevo.return_value = mock_brevo

            response = await admin_client.put(
                f"/api/v1/contacts/{contact_id}",
                json={"status": "active"},
            )

        assert response.status_code == 200

    async def test_update_status_brevo_unblock_fails(
        self, admin_client: AsyncClient, mock_db_session
    ):
        contact_id = uuid4()
        contact = _make_contact_mock(id=contact_id, status="complained", email="c@t.com")
        mock_db_session.get = AsyncMock(return_value=contact)

        reloaded = _make_contact_mock(id=contact_id, status="active")
        reload_result = MagicMock()
        reload_result.scalar_one.return_value = reloaded
        mock_db_session.execute = AsyncMock(return_value=reload_result)

        with patch("mailler.services.providers.brevo.BrevoProvider") as MockBrevo:
            mock_brevo = MagicMock()
            mock_brevo.is_configured = True
            mock_brevo.unblock_contact = AsyncMock(return_value={"success": False, "error": "err"})
            MockBrevo.return_value = mock_brevo

            response = await admin_client.put(
                f"/api/v1/contacts/{contact_id}",
                json={"status": "active"},
            )

        assert response.status_code == 200

    async def test_update_status_no_brevo_unblock_needed(
        self, admin_client: AsyncClient, mock_db_session
    ):
        """Cover lines 406->411: status change that does not require Brevo unblock.

        When old status is 'active' and new status is 'unsubscribed',
        needs_brevo_unblock stays False.
        """
        contact_id = uuid4()
        contact = _make_contact_mock(id=contact_id, status="active", email="a@t.com")
        mock_db_session.get = AsyncMock(return_value=contact)

        reloaded = _make_contact_mock(id=contact_id, status="unsubscribed")
        reload_result = MagicMock()
        reload_result.scalar_one.return_value = reloaded
        mock_db_session.execute = AsyncMock(return_value=reload_result)

        response = await admin_client.put(
            f"/api/v1/contacts/{contact_id}",
            json={"status": "unsubscribed"},
        )
        assert response.status_code == 200

    async def test_update_status_brevo_not_configured(
        self, admin_client: AsyncClient, mock_db_session
    ):
        """Cover lines 422->443: Brevo unblock skipped when provider is not configured.

        When status changes from bounced to active but brevo.is_configured is False,
        the unblock is skipped entirely.
        """
        contact_id = uuid4()
        contact = _make_contact_mock(id=contact_id, status="bounced", email="b@t.com")
        mock_db_session.get = AsyncMock(return_value=contact)

        reloaded = _make_contact_mock(id=contact_id, status="active")
        reload_result = MagicMock()
        reload_result.scalar_one.return_value = reloaded
        mock_db_session.execute = AsyncMock(return_value=reload_result)

        with patch("mailler.services.providers.brevo.BrevoProvider") as MockBrevo:
            mock_brevo = MagicMock()
            mock_brevo.is_configured = False
            MockBrevo.return_value = mock_brevo

            response = await admin_client.put(
                f"/api/v1/contacts/{contact_id}",
                json={"status": "active"},
            )

        assert response.status_code == 200


# --------------------------------------------------------------------------
# DELETE /contacts/{id}
# --------------------------------------------------------------------------


class TestDeleteContact:
    async def test_delete_success(self, admin_client: AsyncClient, mock_db_session):
        contact = _make_contact_mock()
        mock_db_session.get = AsyncMock(return_value=contact)
        response = await admin_client.delete(f"/api/v1/contacts/{contact.id}")
        assert response.status_code == 204

    async def test_delete_not_found(self, admin_client: AsyncClient, mock_db_session):
        mock_db_session.get = AsyncMock(return_value=None)
        response = await admin_client.delete(f"/api/v1/contacts/{uuid4()}")
        assert response.status_code == 404


# --------------------------------------------------------------------------
# POST /contacts/{id}/unsubscribe
# --------------------------------------------------------------------------


class TestUnsubscribeContact:
    async def test_unsubscribe_success(self, admin_client: AsyncClient, mock_db_session):
        contact = _make_contact_mock(status="active")
        mock_db_session.get = AsyncMock(return_value=contact)

        response = await admin_client.post(f"/api/v1/contacts/{contact.id}/unsubscribe")
        assert response.status_code == 200
        assert response.json()["status"] == "unsubscribed"

    async def test_unsubscribe_not_found(self, admin_client: AsyncClient, mock_db_session):
        mock_db_session.get = AsyncMock(return_value=None)
        response = await admin_client.post(f"/api/v1/contacts/{uuid4()}/unsubscribe")
        assert response.status_code == 404


# --------------------------------------------------------------------------
# Isolation between clients
# --------------------------------------------------------------------------


def _params(mock_db_session, call=0):
    return mock_db_session.execute.await_args_list[call].args[0].compile().params


class TestContactsBelongToTheirClient:
    async def test_list_is_restricted_to_the_client(self, auth_client, mock_db_session):
        mock_db_session.execute = AsyncMock(side_effect=_make_db_list_response())
        assert (await auth_client.get("/api/v1/contacts")).status_code == 200
        assert _params(mock_db_session, 0)["client_id_1"] == "test-client-id"
        assert _params(mock_db_session, 1)["client_id_1"] == "test-client-id"

    async def test_list_of_another_client_is_forbidden(self, auth_client):
        assert (await auth_client.get("/api/v1/contacts?client_id=other")).status_code == 403

    async def test_admin_lists_every_client(self, admin_client, mock_db_session):
        mock_db_session.execute = AsyncMock(side_effect=_make_db_list_response())
        await admin_client.get("/api/v1/contacts")
        assert "client_id_1" not in _params(mock_db_session, 1)

    async def test_created_contact_is_owned_by_the_caller(self, writer_client, mock_db_session):
        response = await writer_client.post("/api/v1/contacts", json={"email": "new@example.com"})
        assert response.status_code == 201
        assert mock_db_session.add.call_args[0][0].client_id == "test-client-id"
        assert response.json()["client_id"] == "test-client-id"

    async def test_regular_caller_cannot_create_for_another_client(
        self, writer_client, mock_db_session
    ):
        response = await writer_client.post(
            "/api/v1/contacts?client_id=other", json={"email": "new@example.com"}
        )
        assert response.status_code == 403
        mock_db_session.add.assert_not_called()

    async def test_admin_creates_for_another_client(self, admin_client, mock_db_session):
        response = await admin_client.post(
            "/api/v1/contacts?client_id=other", json={"email": "new@example.com"}
        )
        assert response.status_code == 201
        assert mock_db_session.add.call_args[0][0].client_id == "other"

    async def test_bulk_contacts_belong_to_the_caller(self, writer_client, mock_db_session):
        result = MagicMock()
        result.scalar_one_or_none.return_value = None
        mock_db_session.execute = AsyncMock(return_value=result)
        response = await writer_client.post(
            "/api/v1/contacts/bulk",
            json={"contacts": [{"email": "a@example.com"}, {"email": "b@example.com"}]},
        )
        assert response.status_code == 201
        assert [c.args[0].client_id for c in mock_db_session.add.call_args_list] == [
            "test-client-id",
            "test-client-id",
        ]
        # the duplicate check is made inside the caller's client
        assert _params(mock_db_session)["client_id_1"] == "test-client-id"

    async def test_get_of_another_client_is_not_found(self, auth_client, mock_db_session):
        result = MagicMock()
        result.scalar_one_or_none.return_value = _make_contact_mock(client_id="other")
        mock_db_session.execute = AsyncMock(return_value=result)
        assert (await auth_client.get(f"/api/v1/contacts/{uuid4()}")).status_code == 404

    async def test_admin_reads_any_client(self, admin_client, mock_db_session):
        result = MagicMock()
        result.scalar_one_or_none.return_value = _make_contact_mock(client_id="other")
        mock_db_session.execute = AsyncMock(return_value=result)
        response = await admin_client.get(f"/api/v1/contacts/{uuid4()}")
        assert response.status_code == 200
        assert response.json()["client_id"] == "other"

    async def test_by_email_looks_inside_the_callers_client(self, auth_client, mock_db_session):
        result = MagicMock()
        result.scalar_one_or_none.return_value = None
        mock_db_session.execute = AsyncMock(return_value=result)
        await auth_client.get("/api/v1/contacts/by-email/a@example.com")
        assert _params(mock_db_session)["client_id_1"] == "test-client-id"
        assert _params(mock_db_session)["email_1"] == "a@example.com"

    async def test_by_email_of_another_client_is_forbidden(self, auth_client):
        response = await auth_client.get("/api/v1/contacts/by-email/a@example.com?client_id=other")
        assert response.status_code == 403

    async def test_update_delete_unsubscribe_of_another_client_are_not_found(
        self, writer_client, mock_db_session
    ):
        foreign = _make_contact_mock(client_id="other")
        mock_db_session.get = AsyncMock(return_value=foreign)
        result = MagicMock()
        result.scalar_one_or_none.return_value = foreign
        mock_db_session.execute = AsyncMock(return_value=result)
        assert (
            await writer_client.put(f"/api/v1/contacts/{foreign.id}", json={"first_name": "X"})
        ).status_code == 404
        assert (await writer_client.delete(f"/api/v1/contacts/{foreign.id}")).status_code == 404
        assert (
            await writer_client.post(f"/api/v1/contacts/{foreign.id}/unsubscribe")
        ).status_code == 404
        mock_db_session.delete.assert_not_called()
        assert foreign.status == "active"

    async def test_owner_updates_deletes_and_unsubscribes(self, writer_client, mock_db_session):
        own = _make_contact_mock()
        mock_db_session.get = AsyncMock(return_value=own)
        result = MagicMock()
        result.scalar_one_or_none.return_value = own
        result.scalar_one.return_value = own
        mock_db_session.execute = AsyncMock(return_value=result)
        assert (
            await writer_client.put(f"/api/v1/contacts/{own.id}", json={"first_name": "X"})
        ).status_code == 200
        assert (
            await writer_client.post(f"/api/v1/contacts/{own.id}/unsubscribe")
        ).status_code == 200
        assert (await writer_client.delete(f"/api/v1/contacts/{own.id}")).status_code == 204
