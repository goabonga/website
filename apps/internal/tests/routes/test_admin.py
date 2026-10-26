# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for app/routes/admin.py - Admin routes for Chat History CRUD."""

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.responses import RedirectResponse
from internal.auth.models import User

USER_UUID = uuid.UUID("12345678-1234-5678-1234-567812345678")
CONV_UUID = uuid.UUID("aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee")


def _make_user(**kwargs):
    defaults = {
        "id": USER_UUID,
        "email": "test@example.com",
        "name": "Test",
        "scopes": ["*"],
    }
    defaults.update(kwargs)
    return User(**defaults)


def _make_request(**kwargs):
    req = MagicMock()
    req.query_params = kwargs.get("query_params", {})
    req.headers = kwargs.get("headers", {})
    req.form = AsyncMock(return_value=MagicMock())
    req.cookies = kwargs.get("cookies", {})
    return req


def _make_db():
    db = AsyncMock()
    return db


def _make_conversation(**kwargs):
    conv = MagicMock()
    conv.id = kwargs.get("id", CONV_UUID)
    conv.user_id = kwargs.get("user_id", USER_UUID)
    conv.session_id = kwargs.get("session_id", "sess-123")
    conv.title = kwargs.get("title", "Test Conversation")
    conv.updated_at = MagicMock()
    return conv


def _make_message(**kwargs):
    msg = MagicMock()
    msg.id = kwargs.get("id", uuid.uuid4())
    msg.conversation_id = kwargs.get("conversation_id", CONV_UUID)
    msg.role = kwargs.get("role", "user")
    msg.content = kwargs.get("content", "Hello")
    return msg


# =========================================================================
# Dashboard
# =========================================================================


class TestDashboard:
    @pytest.mark.asyncio
    async def test_redirect_when_not_authenticated(self):
        from internal.routes.admin import dashboard

        req = _make_request()
        db = _make_db()
        redirect = RedirectResponse(url="/auth/login")
        result = await dashboard(request=req, db=db, auth_result=redirect)
        assert isinstance(result, RedirectResponse)

    @pytest.mark.asyncio
    async def test_dashboard_success(self):
        from internal.routes.admin import dashboard

        req = _make_request()
        db = _make_db()
        user = _make_user()

        # db.scalar returns count values
        db.scalar = AsyncMock(side_effect=[10, 50, 7, 3])

        # db.execute returns recent conversations
        conv_mock = _make_conversation()
        result_mock = MagicMock()
        result_mock.all.return_value = [(conv_mock, 5)]
        db.execute = AsyncMock(return_value=result_mock)

        with (
            patch("internal.routes.admin.templates") as mock_templates,
            patch("internal.routes.admin.settings") as mock_settings,
            patch("internal.routes.admin.analytics_client") as mock_analytics,
        ):
            mock_settings.oauth2_client_id = "test-client"
            mock_analytics.get_overview = AsyncMock(return_value={"visits": 100})
            mock_templates.TemplateResponse.return_value = MagicMock()

            await dashboard(request=req, db=db, auth_result=user)

            mock_templates.TemplateResponse.assert_called_once()
            call_kwargs = mock_templates.TemplateResponse.call_args.kwargs
            assert call_kwargs["context"]["stats"]["total_conversations"] == 10
            assert call_kwargs["context"]["stats"]["total_messages"] == 50
            assert call_kwargs["context"]["analytics_stats"] == {"visits": 100}
            assert len(call_kwargs["context"]["recent_conversations"]) == 1

    @pytest.mark.asyncio
    async def test_dashboard_no_analytics_scope(self):
        from internal.routes.admin import dashboard

        req = _make_request()
        db = _make_db()
        user = _make_user(scopes=["conversations:read"])

        db.scalar = AsyncMock(return_value=0)
        result_mock = MagicMock()
        result_mock.all.return_value = []
        db.execute = AsyncMock(return_value=result_mock)

        with (
            patch("internal.routes.admin.templates") as mock_templates,
            patch("internal.routes.admin.settings") as mock_settings,
        ):
            mock_settings.oauth2_client_id = "test-client"
            mock_templates.TemplateResponse.return_value = MagicMock()

            await dashboard(request=req, db=db, auth_result=user)

            call_kwargs = mock_templates.TemplateResponse.call_args.kwargs
            assert call_kwargs["context"]["analytics_stats"] is None

    @pytest.mark.asyncio
    async def test_dashboard_analytics_exception(self):
        from internal.routes.admin import dashboard

        req = _make_request()
        db = _make_db()
        user = _make_user()  # has * scope

        db.scalar = AsyncMock(return_value=0)
        result_mock = MagicMock()
        result_mock.all.return_value = []
        db.execute = AsyncMock(return_value=result_mock)

        with (
            patch("internal.routes.admin.templates") as mock_templates,
            patch("internal.routes.admin.settings") as mock_settings,
            patch("internal.routes.admin.analytics_client") as mock_analytics,
        ):
            mock_settings.oauth2_client_id = "test-client"
            mock_analytics.get_overview = AsyncMock(side_effect=Exception("API down"))
            mock_templates.TemplateResponse.return_value = MagicMock()

            await dashboard(request=req, db=db, auth_result=user)

            call_kwargs = mock_templates.TemplateResponse.call_args.kwargs
            assert call_kwargs["context"]["analytics_stats"] is None

    @pytest.mark.asyncio
    async def test_dashboard_null_stats(self):
        from internal.routes.admin import dashboard

        req = _make_request()
        db = _make_db()
        user = _make_user(scopes=["conversations:read"])

        db.scalar = AsyncMock(return_value=None)
        result_mock = MagicMock()
        result_mock.all.return_value = []
        db.execute = AsyncMock(return_value=result_mock)

        with (
            patch("internal.routes.admin.templates") as mock_templates,
            patch("internal.routes.admin.settings") as mock_settings,
        ):
            mock_settings.oauth2_client_id = "test-client"
            mock_templates.TemplateResponse.return_value = MagicMock()

            await dashboard(request=req, db=db, auth_result=user)

            call_kwargs = mock_templates.TemplateResponse.call_args.kwargs
            assert call_kwargs["context"]["stats"]["total_conversations"] == 0
            assert call_kwargs["context"]["stats"]["total_messages"] == 0


# =========================================================================
# Conversations List
# =========================================================================


class TestConversationsList:
    @pytest.mark.asyncio
    async def test_redirect_when_not_authenticated(self):
        from internal.routes.admin import conversations_list

        req = _make_request()
        db = _make_db()
        redirect = RedirectResponse(url="/auth/login")
        result = await conversations_list(
            request=req, page=1, search=None, type=None, db=db, auth_result=redirect
        )
        assert isinstance(result, RedirectResponse)

    @pytest.mark.asyncio
    async def test_list_no_filters(self):
        from internal.routes.admin import conversations_list

        req = _make_request()
        db = _make_db()
        user = _make_user()

        db.scalar = AsyncMock(return_value=5)
        conv_mock = _make_conversation()
        result_mock = MagicMock()
        result_mock.all.return_value = [(conv_mock, 3)]
        db.execute = AsyncMock(return_value=result_mock)

        with (
            patch("internal.routes.admin.templates") as mock_templates,
            patch("internal.routes.admin.settings") as mock_settings,
        ):
            mock_settings.oauth2_client_id = "test-client"
            mock_templates.TemplateResponse.return_value = MagicMock()

            await conversations_list(
                request=req, page=1, search=None, type=None, db=db, auth_result=user
            )

            call_kwargs = mock_templates.TemplateResponse.call_args.kwargs
            assert call_kwargs["context"]["total"] == 5
            assert len(call_kwargs["context"]["conversations"]) == 1

    @pytest.mark.asyncio
    async def test_list_shows_the_flash_messages(self):
        from internal.routes.admin import conversations_list

        # The delete routes redirect here with ?success= or ?error=
        req = _make_request(query_params={"success": "Done", "error": "Oops"})
        db = _make_db()
        db.scalar = AsyncMock(return_value=0)
        result_mock = MagicMock()
        result_mock.all.return_value = []
        db.execute = AsyncMock(return_value=result_mock)

        with (
            patch("internal.routes.admin.templates") as mock_templates,
            patch("internal.routes.admin.settings") as mock_settings,
        ):
            mock_settings.oauth2_client_id = "test-client"
            mock_templates.TemplateResponse.return_value = MagicMock()

            await conversations_list(
                request=req, page=1, search=None, type=None, db=db, auth_result=_make_user()
            )

            context = mock_templates.TemplateResponse.call_args.kwargs["context"]
            assert context["success"] == "Done"
            assert context["error"] == "Oops"

    @pytest.mark.asyncio
    async def test_list_search_by_uuid(self):
        from internal.routes.admin import conversations_list

        req = _make_request()
        db = _make_db()
        user = _make_user()

        db.scalar = AsyncMock(return_value=1)
        conv_mock = _make_conversation()
        result_mock = MagicMock()
        result_mock.all.return_value = [(conv_mock, 2)]
        db.execute = AsyncMock(return_value=result_mock)

        with (
            patch("internal.routes.admin.templates") as mock_templates,
            patch("internal.routes.admin.settings") as mock_settings,
        ):
            mock_settings.oauth2_client_id = "test-client"
            mock_templates.TemplateResponse.return_value = MagicMock()

            await conversations_list(
                request=req,
                page=1,
                search=str(USER_UUID),
                type=None,
                db=db,
                auth_result=user,
            )

            call_kwargs = mock_templates.TemplateResponse.call_args.kwargs
            assert call_kwargs["context"]["search"] == str(USER_UUID)

    @pytest.mark.asyncio
    async def test_list_search_by_session_id(self):
        from internal.routes.admin import conversations_list

        req = _make_request()
        db = _make_db()
        user = _make_user()

        db.scalar = AsyncMock(return_value=1)
        result_mock = MagicMock()
        result_mock.all.return_value = []
        db.execute = AsyncMock(return_value=result_mock)

        with (
            patch("internal.routes.admin.templates") as mock_templates,
            patch("internal.routes.admin.settings") as mock_settings,
        ):
            mock_settings.oauth2_client_id = "test-client"
            mock_templates.TemplateResponse.return_value = MagicMock()

            await conversations_list(
                request=req,
                page=1,
                search="not-a-uuid",
                type=None,
                db=db,
                auth_result=user,
            )

            call_kwargs = mock_templates.TemplateResponse.call_args.kwargs
            assert call_kwargs["context"]["search"] == "not-a-uuid"

    @pytest.mark.asyncio
    async def test_list_type_authenticated(self):
        from internal.routes.admin import conversations_list

        req = _make_request()
        db = _make_db()
        user = _make_user()

        db.scalar = AsyncMock(return_value=0)
        result_mock = MagicMock()
        result_mock.all.return_value = []
        db.execute = AsyncMock(return_value=result_mock)

        with (
            patch("internal.routes.admin.templates") as mock_templates,
            patch("internal.routes.admin.settings") as mock_settings,
        ):
            mock_settings.oauth2_client_id = "test-client"
            mock_templates.TemplateResponse.return_value = MagicMock()

            await conversations_list(
                request=req,
                page=1,
                search=None,
                type="authenticated",
                db=db,
                auth_result=user,
            )

            call_kwargs = mock_templates.TemplateResponse.call_args.kwargs
            assert call_kwargs["context"]["type_filter"] == "authenticated"

    @pytest.mark.asyncio
    async def test_list_type_anonymous(self):
        from internal.routes.admin import conversations_list

        req = _make_request()
        db = _make_db()
        user = _make_user()

        db.scalar = AsyncMock(return_value=0)
        result_mock = MagicMock()
        result_mock.all.return_value = []
        db.execute = AsyncMock(return_value=result_mock)

        with (
            patch("internal.routes.admin.templates") as mock_templates,
            patch("internal.routes.admin.settings") as mock_settings,
        ):
            mock_settings.oauth2_client_id = "test-client"
            mock_templates.TemplateResponse.return_value = MagicMock()

            await conversations_list(
                request=req,
                page=1,
                search=None,
                type="anonymous",
                db=db,
                auth_result=user,
            )

            call_kwargs = mock_templates.TemplateResponse.call_args.kwargs
            assert call_kwargs["context"]["type_filter"] == "anonymous"

    @pytest.mark.asyncio
    async def test_list_null_total(self):
        from internal.routes.admin import conversations_list

        req = _make_request()
        db = _make_db()
        user = _make_user()

        db.scalar = AsyncMock(return_value=None)
        result_mock = MagicMock()
        result_mock.all.return_value = []
        db.execute = AsyncMock(return_value=result_mock)

        with (
            patch("internal.routes.admin.templates") as mock_templates,
            patch("internal.routes.admin.settings") as mock_settings,
        ):
            mock_settings.oauth2_client_id = "test-client"
            mock_templates.TemplateResponse.return_value = MagicMock()

            await conversations_list(
                request=req, page=1, search=None, type=None, db=db, auth_result=user
            )

            call_kwargs = mock_templates.TemplateResponse.call_args.kwargs
            assert call_kwargs["context"]["total"] == 0
            assert call_kwargs["context"]["total_pages"] == 0


# =========================================================================
# Conversation Detail
# =========================================================================


class TestConversationDetail:
    @pytest.mark.asyncio
    async def test_redirect_when_not_authenticated(self):
        from internal.routes.admin import conversation_detail

        req = _make_request()
        db = _make_db()
        redirect = RedirectResponse(url="/auth/login")
        result = await conversation_detail(
            request=req, conversation_id=CONV_UUID, db=db, auth_result=redirect
        )
        assert isinstance(result, RedirectResponse)

    @pytest.mark.asyncio
    async def test_conversation_not_found(self):
        from internal.routes.admin import conversation_detail

        req = _make_request()
        db = _make_db()
        user = _make_user()

        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = None
        db.execute = AsyncMock(return_value=result_mock)

        with (
            patch("internal.routes.admin.templates") as mock_templates,
            patch("internal.routes.admin.settings") as mock_settings,
        ):
            mock_settings.oauth2_client_id = "test-client"
            mock_templates.TemplateResponse.return_value = MagicMock()

            await conversation_detail(
                request=req, conversation_id=CONV_UUID, db=db, auth_result=user
            )

            call_kwargs = mock_templates.TemplateResponse.call_args.kwargs
            assert call_kwargs["context"]["error"] == "Conversation not found."

    @pytest.mark.asyncio
    async def test_conversation_found_with_owner(self):
        from internal.routes.admin import conversation_detail

        req = _make_request(headers={"referer": "http://test/conversations?page=2"})
        db = _make_db()
        user = _make_user()

        conv = _make_conversation(user_id=USER_UUID)
        msg1 = _make_message(role="user", content="Hello")
        msg2 = _make_message(role="assistant", content="Hi there")
        msg3 = _make_message(role="system", content="System msg")

        # First execute: conversation query
        conv_result = MagicMock()
        conv_result.scalar_one_or_none.return_value = conv
        # Second execute: messages query
        msg_scalars = MagicMock()
        msg_scalars.all.return_value = [msg1, msg2, msg3]
        msg_result = MagicMock()
        msg_result.scalars.return_value = msg_scalars

        db.execute = AsyncMock(side_effect=[conv_result, msg_result])

        owner_mock = MagicMock()
        owner_mock.name = "Owner Name"

        with (
            patch("internal.routes.admin.templates") as mock_templates,
            patch("internal.routes.admin.settings") as mock_settings,
            patch("internal.routes.admin.auth_client") as mock_auth_client,
        ):
            mock_settings.oauth2_client_id = "test-client"
            mock_auth_client.get_user = AsyncMock(return_value=owner_mock)
            mock_templates.TemplateResponse.return_value = MagicMock()

            await conversation_detail(
                request=req, conversation_id=CONV_UUID, db=db, auth_result=user
            )

            call_kwargs = mock_templates.TemplateResponse.call_args.kwargs
            ctx = call_kwargs["context"]
            assert ctx["conversation"] is conv
            assert ctx["owner"] is owner_mock
            assert ctx["user_message_count"] == 1
            assert ctx["assistant_message_count"] == 1
            assert ctx["system_message_count"] == 1
            assert "page=2" in ctx["back_params"]

    @pytest.mark.asyncio
    async def test_conversation_without_owner(self):
        from internal.routes.admin import conversation_detail

        req = _make_request(headers={})
        db = _make_db()
        user = _make_user()

        conv = _make_conversation(user_id=None)

        conv_result = MagicMock()
        conv_result.scalar_one_or_none.return_value = conv
        msg_scalars = MagicMock()
        msg_scalars.all.return_value = []
        msg_result = MagicMock()
        msg_result.scalars.return_value = msg_scalars

        db.execute = AsyncMock(side_effect=[conv_result, msg_result])

        with (
            patch("internal.routes.admin.templates") as mock_templates,
            patch("internal.routes.admin.settings") as mock_settings,
        ):
            mock_settings.oauth2_client_id = "test-client"
            mock_templates.TemplateResponse.return_value = MagicMock()

            await conversation_detail(
                request=req, conversation_id=CONV_UUID, db=db, auth_result=user
            )

            call_kwargs = mock_templates.TemplateResponse.call_args.kwargs
            assert call_kwargs["context"]["owner"] is None
            assert call_kwargs["context"]["back_params"] == ""

    @pytest.mark.asyncio
    async def test_conversation_with_success_param(self):
        from internal.routes.admin import conversation_detail

        req = _make_request(query_params={"success": "Done", "error": None})
        db = _make_db()
        user = _make_user()

        conv = _make_conversation(user_id=None)
        conv_result = MagicMock()
        conv_result.scalar_one_or_none.return_value = conv
        msg_scalars = MagicMock()
        msg_scalars.all.return_value = []
        msg_result = MagicMock()
        msg_result.scalars.return_value = msg_scalars
        db.execute = AsyncMock(side_effect=[conv_result, msg_result])

        with (
            patch("internal.routes.admin.templates") as mock_templates,
            patch("internal.routes.admin.settings") as mock_settings,
        ):
            mock_settings.oauth2_client_id = "test-client"
            mock_templates.TemplateResponse.return_value = MagicMock()

            await conversation_detail(
                request=req, conversation_id=CONV_UUID, db=db, auth_result=user
            )

            call_kwargs = mock_templates.TemplateResponse.call_args.kwargs
            assert call_kwargs["context"]["success"] == "Done"


# =========================================================================
# Delete Conversation
# =========================================================================


class TestDeleteConversation:
    @pytest.mark.asyncio
    async def test_redirect_when_not_authenticated(self):
        from internal.routes.admin import delete_conversation

        req = _make_request()
        db = _make_db()
        redirect = RedirectResponse(url="/auth/login")
        result = await delete_conversation(
            request=req, conversation_id=CONV_UUID, db=db, auth_result=redirect
        )
        assert isinstance(result, RedirectResponse)

    @pytest.mark.asyncio
    async def test_not_found(self):
        from internal.routes.admin import delete_conversation

        req = _make_request()
        db = _make_db()
        user = _make_user()

        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = None
        db.execute = AsyncMock(return_value=result_mock)

        with patch("internal.routes.admin.settings") as mock_settings:
            mock_settings.oauth2_client_id = "test-client"
            result = await delete_conversation(
                request=req, conversation_id=CONV_UUID, db=db, auth_result=user
            )

        assert isinstance(result, RedirectResponse)
        assert result.status_code == 303
        assert "error" in result.headers.get("location", "")

    @pytest.mark.asyncio
    async def test_delete_success(self):
        from internal.routes.admin import delete_conversation

        req = _make_request()
        db = _make_db()
        user = _make_user()

        conv = _make_conversation()
        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = conv
        db.execute = AsyncMock(return_value=result_mock)

        with patch("internal.routes.admin.settings") as mock_settings:
            mock_settings.oauth2_client_id = "test-client"
            result = await delete_conversation(
                request=req, conversation_id=CONV_UUID, db=db, auth_result=user
            )

        assert isinstance(result, RedirectResponse)
        assert result.status_code == 303
        assert "success" in result.headers.get("location", "")
        db.delete.assert_awaited_once_with(conv)
        db.commit.assert_awaited_once()


# =========================================================================
# Bulk Delete Conversations
# =========================================================================


class TestBulkDeleteConversations:
    @pytest.mark.asyncio
    async def test_redirect_when_not_authenticated(self):
        from internal.routes.admin import bulk_delete_conversations

        req = _make_request()
        db = _make_db()
        redirect = RedirectResponse(url="/auth/login")
        result = await bulk_delete_conversations(request=req, db=db, auth_result=redirect)
        assert isinstance(result, RedirectResponse)

    @pytest.mark.asyncio
    async def test_no_ids_selected(self):
        from internal.routes.admin import bulk_delete_conversations

        req = _make_request()
        form_mock = MagicMock()
        form_mock.getlist.return_value = []
        req.form = AsyncMock(return_value=form_mock)
        db = _make_db()
        user = _make_user()

        result = await bulk_delete_conversations(request=req, db=db, auth_result=user)
        assert isinstance(result, RedirectResponse)
        assert "error" in result.headers.get("location", "")
        assert "No+conversations+selected" in result.headers.get("location", "")

    @pytest.mark.asyncio
    async def test_invalid_uuid(self):
        from internal.routes.admin import bulk_delete_conversations

        req = _make_request()
        form_mock = MagicMock()
        form_mock.getlist.return_value = ["not-a-uuid"]
        req.form = AsyncMock(return_value=form_mock)
        db = _make_db()
        user = _make_user()

        result = await bulk_delete_conversations(request=req, db=db, auth_result=user)
        assert isinstance(result, RedirectResponse)
        assert "Invalid" in result.headers.get("location", "")

    @pytest.mark.asyncio
    async def test_no_conversations_found(self):
        from internal.routes.admin import bulk_delete_conversations

        req = _make_request()
        form_mock = MagicMock()
        form_mock.getlist.return_value = [str(CONV_UUID)]
        req.form = AsyncMock(return_value=form_mock)
        db = _make_db()
        user = _make_user()

        scalars_mock = MagicMock()
        scalars_mock.all.return_value = []
        result_mock = MagicMock()
        result_mock.scalars.return_value = scalars_mock
        db.execute = AsyncMock(return_value=result_mock)

        with patch("internal.routes.admin.settings") as mock_settings:
            mock_settings.oauth2_client_id = "test-client"
            result = await bulk_delete_conversations(request=req, db=db, auth_result=user)

        assert isinstance(result, RedirectResponse)
        assert "No+conversations+found" in result.headers.get("location", "")

    @pytest.mark.asyncio
    async def test_bulk_delete_success(self):
        from internal.routes.admin import bulk_delete_conversations

        req = _make_request()
        form_mock = MagicMock()
        uuid2 = uuid.uuid4()
        form_mock.getlist.return_value = [str(CONV_UUID), str(uuid2)]
        req.form = AsyncMock(return_value=form_mock)
        db = _make_db()
        user = _make_user()

        conv1 = _make_conversation(id=CONV_UUID)
        conv2 = _make_conversation(id=uuid2)
        scalars_mock = MagicMock()
        scalars_mock.all.return_value = [conv1, conv2]
        result_mock = MagicMock()
        result_mock.scalars.return_value = scalars_mock
        db.execute = AsyncMock(return_value=result_mock)

        with patch("internal.routes.admin.settings") as mock_settings:
            mock_settings.oauth2_client_id = "test-client"
            result = await bulk_delete_conversations(request=req, db=db, auth_result=user)

        assert isinstance(result, RedirectResponse)
        assert result.status_code == 303
        assert "2+conversation(s)+deleted" in result.headers.get("location", "")
        assert db.delete.await_count == 2
        db.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_bulk_delete_comma_separated_selection(self):
        from internal.routes.admin import bulk_delete_conversations

        # The list page sends the whole selection as one comma-separated value
        req = _make_request()
        form_mock = MagicMock()
        uuid2 = uuid.uuid4()
        form_mock.getlist.return_value = [f"{CONV_UUID},{uuid2}"]
        req.form = AsyncMock(return_value=form_mock)
        db = _make_db()
        user = _make_user()

        scalars_mock = MagicMock()
        scalars_mock.all.return_value = [
            _make_conversation(id=CONV_UUID),
            _make_conversation(id=uuid2),
        ]
        result_mock = MagicMock()
        result_mock.scalars.return_value = scalars_mock
        db.execute = AsyncMock(return_value=result_mock)

        with patch("internal.routes.admin.settings") as mock_settings:
            mock_settings.oauth2_client_id = "test-client"
            result = await bulk_delete_conversations(request=req, db=db, auth_result=user)

        assert "2+conversation(s)+deleted" in result.headers.get("location", "")
        assert db.delete.await_count == 2

    @pytest.mark.asyncio
    async def test_bulk_delete_empty_id_in_list(self):
        from internal.routes.admin import bulk_delete_conversations

        req = _make_request()
        form_mock = MagicMock()
        form_mock.getlist.return_value = [str(CONV_UUID), ""]
        req.form = AsyncMock(return_value=form_mock)
        db = _make_db()
        user = _make_user()

        conv = _make_conversation()
        scalars_mock = MagicMock()
        scalars_mock.all.return_value = [conv]
        result_mock = MagicMock()
        result_mock.scalars.return_value = scalars_mock
        db.execute = AsyncMock(return_value=result_mock)

        with patch("internal.routes.admin.settings") as mock_settings:
            mock_settings.oauth2_client_id = "test-client"
            result = await bulk_delete_conversations(request=req, db=db, auth_result=user)

        assert isinstance(result, RedirectResponse)
        assert "success" in result.headers.get("location", "")


class TestConversationDetailPage:
    def test_message_markup_is_escaped_and_kept_without_scripts(self):
        from datetime import datetime

        from internal.routes.admin import templates

        message = MagicMock()
        message.role = "user"
        message.content = "<img src=x onerror=alert(1)> **hi**"
        message.created_at = datetime(2024, 1, 1)
        conversation = MagicMock()
        conversation.id = CONV_UUID
        conversation.user_id = None
        conversation.session_id = "sess-123"
        conversation.title = "Title"
        conversation.created_at = datetime(2024, 1, 1)
        conversation.updated_at = datetime(2024, 1, 1)

        html = templates.env.get_template("admin/conversations/detail.html").render(
            user=_make_user(),
            conversation=conversation,
            owner=None,
            messages=[message],
            user_message_count=1,
            assistant_message_count=0,
            system_message_count=0,
            back_params="",
        )

        # The text is in the page whether or not the markdown libraries load, never as markup
        assert "<img src=x" not in html
        assert "&lt;img src=x onerror=alert(1)&gt; **hi**</div>" in html
