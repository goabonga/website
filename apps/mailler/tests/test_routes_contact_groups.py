# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for contact group CRUD routes."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

from httpx import AsyncClient
from sqlalchemy.exc import IntegrityError


def _make_db_list_response(items=None, total=0):
    count_result = MagicMock()
    count_result.scalar.return_value = total
    list_result = MagicMock()
    list_result.scalars.return_value.all.return_value = items or []
    return [count_result, list_result]


def _make_group_mock(**overrides):
    now = datetime.now(UTC)
    g = MagicMock()
    g.id = overrides.get("id", 1)
    g.client_id = overrides.get("client_id", "test-client-id")
    g.slug = overrides.get("slug", "test-group")
    g.name = overrides.get("name", "Test Group")
    g.description = overrides.get("description")
    g.is_dynamic = overrides.get("is_dynamic", False)
    g.filter_criteria = overrides.get("filter_criteria")
    g.member_count = overrides.get("member_count", 0)
    g.members = overrides.get("members", [])
    g.created_at = overrides.get("created_at", now)
    g.updated_at = overrides.get("updated_at", now)
    return g


def _make_contact_mock(**overrides):
    now = datetime.now(UTC)
    c = MagicMock()
    c.id = overrides.get("id", uuid4())
    c.client_id = overrides.get("client_id", "test-client-id")
    c.email = overrides.get("email", "c@t.com")
    c.first_name = overrides.get("first_name", "First")
    c.last_name = overrides.get("last_name", "Last")
    c.status = overrides.get("status", "active")
    c.source = overrides.get("source", "api")
    c.created_at = overrides.get("created_at", now)
    return c


# --------------------------------------------------------------------------
# GET /contact-groups
# --------------------------------------------------------------------------


class TestListContactGroups:
    async def test_list_empty(self, auth_client: AsyncClient, mock_db_session):
        mock_db_session.execute = AsyncMock(side_effect=_make_db_list_response(items=[], total=0))
        response = await auth_client.get("/api/v1/contact-groups")
        assert response.status_code == 200
        assert response.json()["items"] == []

    async def test_list_with_items(self, auth_client: AsyncClient, mock_db_session):
        group = _make_group_mock()
        mock_db_session.execute = AsyncMock(
            side_effect=_make_db_list_response(items=[group], total=1)
        )
        response = await auth_client.get("/api/v1/contact-groups")
        assert response.status_code == 200
        assert len(response.json()["items"]) == 1

    async def test_list_with_search(self, auth_client: AsyncClient, mock_db_session):
        mock_db_session.execute = AsyncMock(side_effect=_make_db_list_response(items=[], total=0))
        response = await auth_client.get("/api/v1/contact-groups?search=test")
        assert response.status_code == 200


# --------------------------------------------------------------------------
# POST /contact-groups
# --------------------------------------------------------------------------


class TestCreateContactGroup:
    async def test_create_success(self, admin_client: AsyncClient, mock_db_session):
        async def _mock_refresh(obj, *args, **kwargs):
            if getattr(obj, "id", None) is None:
                obj.id = 1
            if getattr(obj, "created_at", None) is None:
                obj.created_at = datetime.now(UTC)
            if getattr(obj, "updated_at", None) is None:
                obj.updated_at = datetime.now(UTC)
            if getattr(obj, "member_count", None) is None:
                obj.member_count = 0

        mock_db_session.refresh = AsyncMock(side_effect=_mock_refresh)

        response = await admin_client.post(
            "/api/v1/contact-groups",
            json={"slug": "grp", "name": "Group"},
        )
        assert response.status_code == 201
        data = response.json()
        assert data["slug"] == "grp"
        assert data["name"] == "Group"

    async def test_create_duplicate_slug(self, admin_client: AsyncClient, mock_db_session):
        mock_db_session.commit = AsyncMock(side_effect=IntegrityError("", {}, Exception()))
        response = await admin_client.post(
            "/api/v1/contact-groups",
            json={"slug": "existing", "name": "Dup"},
        )
        assert response.status_code == 409


# --------------------------------------------------------------------------
# GET /contact-groups/{id}
# --------------------------------------------------------------------------


class TestGetContactGroup:
    async def test_get_found(self, auth_client: AsyncClient, mock_db_session):
        mock_db_session.get = AsyncMock(return_value=_make_group_mock())
        response = await auth_client.get("/api/v1/contact-groups/1")
        assert response.status_code == 200
        assert response.json()["slug"] == "test-group"

    async def test_get_not_found(self, auth_client: AsyncClient, mock_db_session):
        mock_db_session.get = AsyncMock(return_value=None)
        response = await auth_client.get("/api/v1/contact-groups/999")
        assert response.status_code == 404


# --------------------------------------------------------------------------
# GET /contact-groups/by-slug/{slug}
# --------------------------------------------------------------------------


class TestGetContactGroupBySlug:
    async def test_found(self, auth_client: AsyncClient, mock_db_session):
        group = _make_group_mock()
        result = MagicMock()
        result.scalar_one_or_none.return_value = group
        mock_db_session.execute = AsyncMock(return_value=result)

        response = await auth_client.get("/api/v1/contact-groups/by-slug/test-group")
        assert response.status_code == 200
        assert response.json()["slug"] == "test-group"

    async def test_not_found(self, auth_client: AsyncClient, mock_db_session):
        result = MagicMock()
        result.scalar_one_or_none.return_value = None
        mock_db_session.execute = AsyncMock(return_value=result)

        response = await auth_client.get("/api/v1/contact-groups/by-slug/nope")
        assert response.status_code == 404


# --------------------------------------------------------------------------
# PUT /contact-groups/{id}
# --------------------------------------------------------------------------


class TestUpdateContactGroup:
    async def test_update_success(self, admin_client: AsyncClient, mock_db_session):
        group = _make_group_mock()
        mock_db_session.get = AsyncMock(return_value=group)

        response = await admin_client.put(
            "/api/v1/contact-groups/1",
            json={
                "name": "Updated",
                "slug": "updated",
                "description": "Desc",
                "is_dynamic": True,
                "filter_criteria": {"status": "active"},
            },
        )
        assert response.status_code == 200

    async def test_update_not_found(self, admin_client: AsyncClient, mock_db_session):
        mock_db_session.get = AsyncMock(return_value=None)
        response = await admin_client.put("/api/v1/contact-groups/999", json={"name": "X"})
        assert response.status_code == 404

    async def test_update_duplicate_slug(self, admin_client: AsyncClient, mock_db_session):
        group = _make_group_mock()
        mock_db_session.get = AsyncMock(return_value=group)
        mock_db_session.commit = AsyncMock(side_effect=IntegrityError("", {}, Exception()))

        response = await admin_client.put("/api/v1/contact-groups/1", json={"slug": "existing"})
        assert response.status_code == 409

    async def test_update_without_slug(self, admin_client: AsyncClient, mock_db_session):
        """Cover branch 262->264: update without providing slug (slug is None in request)."""
        group = _make_group_mock()
        mock_db_session.get = AsyncMock(return_value=group)

        response = await admin_client.put(
            "/api/v1/contact-groups/1", json={"name": "Only Name Updated"}
        )
        assert response.status_code == 200
        assert response.json()["name"] == "Only Name Updated"


# --------------------------------------------------------------------------
# DELETE /contact-groups/{id}
# --------------------------------------------------------------------------


class TestDeleteContactGroup:
    async def test_delete_success(self, admin_client: AsyncClient, mock_db_session):
        group = _make_group_mock()
        mock_db_session.get = AsyncMock(return_value=group)
        response = await admin_client.delete("/api/v1/contact-groups/1")
        assert response.status_code == 204

    async def test_delete_not_found(self, admin_client: AsyncClient, mock_db_session):
        mock_db_session.get = AsyncMock(return_value=None)
        response = await admin_client.delete("/api/v1/contact-groups/999")
        assert response.status_code == 404


# --------------------------------------------------------------------------
# GET /contact-groups/{id}/contacts
# --------------------------------------------------------------------------


class TestListGroupContacts:
    async def test_list_empty(self, auth_client: AsyncClient, mock_db_session):
        mock_db_session.get = AsyncMock(return_value=_make_group_mock())
        mock_db_session.execute = AsyncMock(side_effect=_make_db_list_response(items=[], total=0))
        response = await auth_client.get("/api/v1/contact-groups/1/contacts")
        assert response.status_code == 200
        assert response.json()["items"] == []

    async def test_list_with_contacts(self, auth_client: AsyncClient, mock_db_session):
        contact = _make_contact_mock()
        mock_db_session.get = AsyncMock(return_value=_make_group_mock())
        mock_db_session.execute = AsyncMock(
            side_effect=_make_db_list_response(items=[contact], total=1)
        )
        response = await auth_client.get("/api/v1/contact-groups/1/contacts")
        assert response.status_code == 200
        assert len(response.json()["items"]) == 1

    async def test_list_group_not_found(self, auth_client: AsyncClient, mock_db_session):
        mock_db_session.get = AsyncMock(return_value=None)
        response = await auth_client.get("/api/v1/contact-groups/999/contacts")
        assert response.status_code == 404

    async def test_list_with_search(self, auth_client: AsyncClient, mock_db_session):
        mock_db_session.get = AsyncMock(return_value=_make_group_mock())
        mock_db_session.execute = AsyncMock(side_effect=_make_db_list_response(items=[], total=0))
        response = await auth_client.get("/api/v1/contact-groups/1/contacts?search=test")
        assert response.status_code == 200


# --------------------------------------------------------------------------
# GET /contact-groups/{id}/available-contacts
# --------------------------------------------------------------------------


class TestListAvailableContacts:
    async def test_list_available(self, auth_client: AsyncClient, mock_db_session):
        mock_db_session.get = AsyncMock(return_value=_make_group_mock())
        mock_db_session.execute = AsyncMock(side_effect=_make_db_list_response(items=[], total=0))
        response = await auth_client.get("/api/v1/contact-groups/1/available-contacts")
        assert response.status_code == 200

    async def test_list_available_group_not_found(self, auth_client: AsyncClient, mock_db_session):
        mock_db_session.get = AsyncMock(return_value=None)
        response = await auth_client.get("/api/v1/contact-groups/999/available-contacts")
        assert response.status_code == 404

    async def test_list_available_with_search(self, auth_client: AsyncClient, mock_db_session):
        mock_db_session.get = AsyncMock(return_value=_make_group_mock())
        mock_db_session.execute = AsyncMock(side_effect=_make_db_list_response(items=[], total=0))
        response = await auth_client.get("/api/v1/contact-groups/1/available-contacts?search=test")
        assert response.status_code == 200


# --------------------------------------------------------------------------
# POST /contact-groups/{id}/contacts  (add)
# --------------------------------------------------------------------------


class TestAddContactsToGroup:
    async def test_add_success(self, admin_client: AsyncClient, mock_db_session):
        contact_id = str(uuid4())
        group = _make_group_mock()
        contact = _make_contact_mock(id=contact_id)

        mock_db_session.get = AsyncMock(side_effect=[group, contact])

        # Existing membership check returns None (not a member)
        existing_result = MagicMock()
        existing_result.scalar_one_or_none.return_value = None
        mock_db_session.execute = AsyncMock(return_value=existing_result)

        response = await admin_client.post(
            "/api/v1/contact-groups/1/contacts",
            json={"contact_ids": [contact_id]},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["added"] == 1
        assert data["skipped"] == 0

    async def test_add_contact_not_found(self, admin_client: AsyncClient, mock_db_session):
        group = _make_group_mock()
        mock_db_session.get = AsyncMock(side_effect=[group, None])

        response = await admin_client.post(
            "/api/v1/contact-groups/1/contacts",
            json={"contact_ids": [str(uuid4())]},
        )
        assert response.status_code == 200
        assert response.json()["skipped"] == 1

    async def test_add_already_member(self, admin_client: AsyncClient, mock_db_session):
        contact_id = str(uuid4())
        group = _make_group_mock()
        contact = _make_contact_mock(id=contact_id)

        mock_db_session.get = AsyncMock(side_effect=[group, contact])

        existing_result = MagicMock()
        existing_result.scalar_one_or_none.return_value = MagicMock()  # Already exists
        mock_db_session.execute = AsyncMock(return_value=existing_result)

        response = await admin_client.post(
            "/api/v1/contact-groups/1/contacts",
            json={"contact_ids": [contact_id]},
        )
        assert response.status_code == 200
        assert response.json()["skipped"] == 1

    async def test_add_group_not_found(self, admin_client: AsyncClient, mock_db_session):
        mock_db_session.get = AsyncMock(return_value=None)
        response = await admin_client.post(
            "/api/v1/contact-groups/999/contacts",
            json={"contact_ids": [str(uuid4())]},
        )
        assert response.status_code == 404


# --------------------------------------------------------------------------
# DELETE /contact-groups/{id}/contacts  (remove)
# --------------------------------------------------------------------------


class TestRemoveContactsFromGroup:
    async def test_remove_success(self, admin_client: AsyncClient, mock_db_session):
        group = _make_group_mock()
        mock_db_session.get = AsyncMock(return_value=group)

        membership = MagicMock()
        result = MagicMock()
        result.scalar_one_or_none.return_value = membership
        mock_db_session.execute = AsyncMock(return_value=result)

        response = await admin_client.request(
            "DELETE",
            "/api/v1/contact-groups/1/contacts",
            json={"contact_ids": [str(uuid4())]},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["removed"] == 1
        assert data["skipped"] == 0

    async def test_remove_not_member(self, admin_client: AsyncClient, mock_db_session):
        group = _make_group_mock()
        mock_db_session.get = AsyncMock(return_value=group)

        result = MagicMock()
        result.scalar_one_or_none.return_value = None
        mock_db_session.execute = AsyncMock(return_value=result)

        response = await admin_client.request(
            "DELETE",
            "/api/v1/contact-groups/1/contacts",
            json={"contact_ids": [str(uuid4())]},
        )
        assert response.status_code == 200
        assert response.json()["skipped"] == 1

    async def test_remove_group_not_found(self, admin_client: AsyncClient, mock_db_session):
        mock_db_session.get = AsyncMock(return_value=None)
        response = await admin_client.request(
            "DELETE",
            "/api/v1/contact-groups/999/contacts",
            json={"contact_ids": [str(uuid4())]},
        )
        assert response.status_code == 404


# --------------------------------------------------------------------------
# Isolation between clients
# --------------------------------------------------------------------------


def _params(mock_db_session, call=0):
    return mock_db_session.execute.await_args_list[call].args[0].compile().params


async def _refresh_group(obj, *args, **kwargs):
    obj.id = 1
    obj.created_at = datetime.now(UTC)
    obj.updated_at = datetime.now(UTC)


class TestGroupsBelongToTheirClient:
    async def test_list_is_restricted_to_the_client(self, auth_client, mock_db_session):
        mock_db_session.execute = AsyncMock(side_effect=_make_db_list_response())
        assert (await auth_client.get("/api/v1/contact-groups")).status_code == 200
        assert _params(mock_db_session, 0)["client_id_1"] == "test-client-id"
        assert _params(mock_db_session, 1)["client_id_1"] == "test-client-id"

    async def test_list_of_another_client_is_forbidden(self, auth_client):
        assert (await auth_client.get("/api/v1/contact-groups?client_id=other")).status_code == 403

    async def test_admin_lists_every_client(self, admin_client, mock_db_session):
        mock_db_session.execute = AsyncMock(side_effect=_make_db_list_response())
        await admin_client.get("/api/v1/contact-groups")
        assert "client_id_1" not in _params(mock_db_session, 1)

    async def test_created_group_is_owned_by_the_caller(self, writer_client, mock_db_session):
        mock_db_session.refresh = AsyncMock(side_effect=_refresh_group)
        response = await writer_client.post(
            "/api/v1/contact-groups", json={"slug": "vip", "name": "VIP"}
        )
        assert response.status_code == 201
        assert mock_db_session.add.call_args[0][0].client_id == "test-client-id"

    async def test_regular_caller_cannot_create_for_another_client(
        self, writer_client, mock_db_session
    ):
        response = await writer_client.post(
            "/api/v1/contact-groups?client_id=other", json={"slug": "vip", "name": "VIP"}
        )
        assert response.status_code == 403
        mock_db_session.add.assert_not_called()

    async def test_admin_creates_for_another_client(self, admin_client, mock_db_session):
        mock_db_session.refresh = AsyncMock(side_effect=_refresh_group)
        response = await admin_client.post(
            "/api/v1/contact-groups?client_id=other", json={"slug": "vip", "name": "VIP"}
        )
        assert response.status_code == 201
        assert mock_db_session.add.call_args[0][0].client_id == "other"

    async def test_group_of_another_client_is_not_found_everywhere(
        self, writer_client, mock_db_session
    ):
        foreign = _make_group_mock(client_id="other")
        mock_db_session.get = AsyncMock(return_value=foreign)
        mock_db_session.execute = AsyncMock(side_effect=_make_db_list_response() * 3)
        assert (await writer_client.get("/api/v1/contact-groups/1")).status_code == 404
        assert (
            await writer_client.put("/api/v1/contact-groups/1", json={"name": "Hijacked"})
        ).status_code == 404
        assert (await writer_client.delete("/api/v1/contact-groups/1")).status_code == 404
        assert (await writer_client.get("/api/v1/contact-groups/1/contacts")).status_code == 404
        assert (
            await writer_client.get("/api/v1/contact-groups/1/available-contacts")
        ).status_code == 404
        body = {"contact_ids": [str(uuid4())]}
        assert (
            await writer_client.post("/api/v1/contact-groups/1/contacts", json=body)
        ).status_code == 404
        assert (
            await writer_client.request("DELETE", "/api/v1/contact-groups/1/contacts", json=body)
        ).status_code == 404
        mock_db_session.delete.assert_not_called()
        assert foreign.name != "Hijacked"

    async def test_by_slug_looks_inside_the_callers_client(self, auth_client, mock_db_session):
        result = MagicMock()
        result.scalar_one_or_none.return_value = None
        mock_db_session.execute = AsyncMock(return_value=result)
        await auth_client.get("/api/v1/contact-groups/by-slug/vip")
        assert _params(mock_db_session)["client_id_1"] == "test-client-id"
        assert _params(mock_db_session)["slug_1"] == "vip"

    async def test_by_slug_of_another_client_is_forbidden(self, auth_client):
        response = await auth_client.get("/api/v1/contact-groups/by-slug/vip?client_id=other")
        assert response.status_code == 403

    async def test_available_contacts_stay_inside_the_group_client(
        self, auth_client, mock_db_session
    ):
        mock_db_session.get = AsyncMock(return_value=_make_group_mock())
        mock_db_session.execute = AsyncMock(side_effect=_make_db_list_response())
        assert (
            await auth_client.get("/api/v1/contact-groups/1/available-contacts")
        ).status_code == 200
        for call in (0, 1):
            assert _params(mock_db_session, call)["client_id_1"] == "test-client-id"

    async def test_contacts_of_another_client_cannot_join_a_group(
        self, writer_client, mock_db_session
    ):
        contact_id = str(uuid4())
        mock_db_session.get = AsyncMock(
            side_effect=[_make_group_mock(), _make_contact_mock(id=contact_id, client_id="other")]
        )
        response = await writer_client.post(
            "/api/v1/contact-groups/1/contacts", json={"contact_ids": [contact_id]}
        )
        assert response.status_code == 200
        assert response.json() == {"added": 0, "removed": 0, "skipped": 1}
        mock_db_session.add.assert_not_called()
