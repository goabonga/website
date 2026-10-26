# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for auth.api.routes.auth.register — Registration endpoints."""

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from tests.conftest import make_user

MODULE = "auth.api.routes.auth.register"

# All optional form fields needed when calling register_submit directly
OPTIONAL_FIELDS = {
    "middle_name": None,
    "preferred_username": None,
    "profile_url": None,
    "picture_url": None,
    "website": None,
    "gender": None,
    "birthdate": None,
    "zoneinfo": None,
    "locale": None,
    "address_street": None,
    "address_locality": None,
    "address_region": None,
    "address_postal_code": None,
    "address_country": None,
    "phone_number": None,
    "avatar": None,
    "next": "",
}


def _mock_request(host="10.0.0.1"):
    request = MagicMock()
    request.client = MagicMock()
    request.client.host = host
    request.headers = MagicMock()
    request.headers.get = MagicMock(return_value="TestAgent/1.0")
    request.base_url = "https://auth.example.com/"
    return request


# ---------------------------------------------------------------------------
# get_tenant_prefix / get_current_tenant_id
# ---------------------------------------------------------------------------


class TestHelpers:
    @patch(f"{MODULE}.get_tenant_context", return_value=None)
    def test_get_tenant_prefix_no_context(self, _):
        from auth.api.routes.auth.register import get_tenant_prefix

        assert get_tenant_prefix() == ""

    @patch(f"{MODULE}.get_tenant_context")
    def test_get_tenant_prefix_path(self, mock_ctx):
        from auth.api.routes.auth.register import get_tenant_prefix

        ctx = MagicMock()
        ctx.tenant_slug = "test"
        ctx.resolution_method = "path"
        mock_ctx.return_value = ctx
        assert get_tenant_prefix() == "/t/test"

    @patch(f"{MODULE}.get_tenant_context", return_value=None)
    def test_get_current_tenant_id_no_context(self, _):
        from auth.api.routes.auth.register import get_current_tenant_id

        assert get_current_tenant_id() is None

    @patch(f"{MODULE}.get_tenant_context")
    def test_get_current_tenant_id_with_context(self, mock_ctx):
        from auth.api.routes.auth.register import get_current_tenant_id

        ctx = MagicMock()
        ctx.tenant_id = "t-1"
        mock_ctx.return_value = ctx
        assert get_current_tenant_id() == "t-1"


# ---------------------------------------------------------------------------
# register_form
# ---------------------------------------------------------------------------


class TestRegisterForm:
    @pytest.mark.asyncio
    @patch(f"{MODULE}.get_current_tenant_id", return_value=None)
    @patch(f"{MODULE}.get_tenant_prefix", return_value="")
    async def test_renders_form(self, mock_prefix, mock_tid):
        from auth.api.routes.auth.register import register_form

        request = _mock_request()
        db = AsyncMock()
        branding_svc = MagicMock()
        branding_svc.render_template = AsyncMock(return_value="<html>register</html>")

        result = await register_form(request, db, branding_svc)

        assert result.status_code == 200
        branding_svc.render_template.assert_awaited_once()


# ---------------------------------------------------------------------------
# register_submit
# ---------------------------------------------------------------------------


class TestRegisterSubmit:
    @pytest.mark.asyncio
    @patch(f"{MODULE}.get_current_tenant_id", return_value=None)
    @patch(f"{MODULE}.get_tenant_prefix", return_value="")
    async def test_password_mismatch(self, mock_prefix, mock_tid):
        from auth.api.routes.auth.register import register_submit

        request = _mock_request()
        db = AsyncMock()
        user_svc = MagicMock()
        email_svc = MagicMock()
        branding_svc = MagicMock()
        branding_svc.render_template = AsyncMock(return_value="<html>error</html>")
        profile_svc = MagicMock()

        result = await register_submit(
            request,
            "test@example.com",
            "P@ssw0rd!",
            "DifferentPass1!",
            "nick",
            "John",
            "Doe",
            **OPTIONAL_FIELDS,
            db=db,
            user_service=user_svc,
            email_service=email_svc,
            branding_service=branding_svc,
            profile_service=profile_svc,
        )

        assert result.status_code == 400

    @pytest.mark.asyncio
    @patch(f"{MODULE}.get_current_tenant_id", return_value=None)
    @patch(f"{MODULE}.get_tenant_prefix", return_value="")
    async def test_invalid_password_too_short(self, mock_prefix, mock_tid):
        from auth.api.routes.auth.register import register_submit

        request = _mock_request()
        db = AsyncMock()
        user_svc = MagicMock()
        email_svc = MagicMock()
        branding_svc = MagicMock()
        branding_svc.render_template = AsyncMock(return_value="<html>error</html>")
        profile_svc = MagicMock()

        result = await register_submit(
            request,
            "test@example.com",
            "short",
            "short",
            "nick",
            "John",
            "Doe",
            **OPTIONAL_FIELDS,
            db=db,
            user_service=user_svc,
            email_service=email_svc,
            branding_service=branding_svc,
            profile_service=profile_svc,
        )

        assert result.status_code == 400

    @pytest.mark.asyncio
    @patch(f"{MODULE}.get_current_tenant_id", return_value=None)
    @patch(f"{MODULE}.get_tenant_prefix", return_value="")
    async def test_success_redirect(self, mock_prefix, mock_tid):
        from auth.api.routes.auth.register import register_submit

        user = make_user()
        request = _mock_request()
        db = AsyncMock()
        user_svc = MagicMock()
        user_svc.create_user = AsyncMock(return_value=user)
        email_svc = MagicMock()
        email_svc.send_verification_email = AsyncMock()
        branding_svc = MagicMock()
        profile_svc = MagicMock()

        result = await register_submit(
            request,
            "test@example.com",
            "P@ssw0rd!",
            "P@ssw0rd!",
            "nick",
            "John",
            "Doe",
            **OPTIONAL_FIELDS,
            db=db,
            user_service=user_svc,
            email_service=email_svc,
            branding_service=branding_svc,
            profile_service=profile_svc,
        )

        assert result.status_code == 303
        assert "verify-email" in result.headers.get("location", "")

    @pytest.mark.asyncio
    @patch(f"{MODULE}.get_current_tenant_id", return_value=None)
    @patch(f"{MODULE}.get_tenant_prefix", return_value="")
    async def test_user_creation_fails(self, mock_prefix, mock_tid):
        from auth.api.routes.auth.register import register_submit

        request = _mock_request()
        db = AsyncMock()
        user_svc = MagicMock()
        user_svc.create_user = AsyncMock(side_effect=ValueError("Email already exists"))
        email_svc = MagicMock()
        branding_svc = MagicMock()
        branding_svc.render_template = AsyncMock(return_value="<html>error</html>")
        profile_svc = MagicMock()

        result = await register_submit(
            request,
            "test@example.com",
            "P@ssw0rd!",
            "P@ssw0rd!",
            "nick",
            "John",
            "Doe",
            **OPTIONAL_FIELDS,
            db=db,
            user_service=user_svc,
            email_service=email_svc,
            branding_service=branding_svc,
            profile_service=profile_svc,
        )

        assert result.status_code == 400

    @pytest.mark.asyncio
    @patch(f"{MODULE}.upload_service")
    @patch(f"{MODULE}.get_current_tenant_id", return_value=None)
    @patch(f"{MODULE}.get_tenant_prefix", return_value="")
    async def test_success_with_avatar(self, mock_prefix, mock_tid, mock_upload):
        from auth.api.routes.auth.register import register_submit

        user = make_user()
        request = _mock_request()
        db = AsyncMock()
        user_svc = MagicMock()
        user_svc.create_user = AsyncMock(return_value=user)
        email_svc = MagicMock()
        email_svc.send_verification_email = AsyncMock()
        branding_svc = MagicMock()
        profile_svc = MagicMock()
        profile_svc.update_profile = AsyncMock()

        mock_upload.save_avatar = AsyncMock(return_value="avatars/test.jpg")
        mock_upload.get_avatar_url.return_value = "/uploads/avatars/test.jpg"

        avatar = MagicMock()
        avatar.filename = "test.jpg"

        opts = {**OPTIONAL_FIELDS, "avatar": avatar}
        result = await register_submit(
            request,
            "test@example.com",
            "P@ssw0rd!",
            "P@ssw0rd!",
            "nick",
            "John",
            "Doe",
            **opts,
            db=db,
            user_service=user_svc,
            email_service=email_svc,
            branding_service=branding_svc,
            profile_service=profile_svc,
        )

        assert result.status_code == 303
        mock_upload.save_avatar.assert_awaited_once()

    @pytest.mark.asyncio
    @patch(f"{MODULE}.upload_service")
    @patch(f"{MODULE}.get_current_tenant_id", return_value=None)
    @patch(f"{MODULE}.get_tenant_prefix", return_value="")
    async def test_avatar_upload_failure_continues(self, mock_prefix, mock_tid, mock_upload):
        from auth.api.routes.auth.register import register_submit
        from auth.services.upload import UploadError

        user = make_user()
        request = _mock_request()
        db = AsyncMock()
        user_svc = MagicMock()
        user_svc.create_user = AsyncMock(return_value=user)
        email_svc = MagicMock()
        email_svc.send_verification_email = AsyncMock()
        branding_svc = MagicMock()
        profile_svc = MagicMock()

        mock_upload.save_avatar = AsyncMock(side_effect=UploadError("too large"))

        avatar = MagicMock()
        avatar.filename = "big.jpg"

        opts = {**OPTIONAL_FIELDS, "avatar": avatar}
        result = await register_submit(
            request,
            "test@example.com",
            "P@ssw0rd!",
            "P@ssw0rd!",
            "nick",
            "John",
            "Doe",
            **opts,
            db=db,
            user_service=user_svc,
            email_service=email_svc,
            branding_service=branding_svc,
            profile_service=profile_svc,
        )

        # Registration should succeed despite avatar failure
        assert result.status_code == 303


# ---------------------------------------------------------------------------
# register_api
# ---------------------------------------------------------------------------


class TestRegisterApi:
    @pytest.mark.asyncio
    @patch(f"{MODULE}.settings")
    @patch(f"{MODULE}.get_current_tenant_id", return_value=None)
    async def test_success(self, mock_tid, mock_settings):
        from auth.api.routes.auth.register import register_api
        from auth.api.schemas.auth import ProfileFields, RegisterRequest

        mock_settings.issuer = "https://auth.example.com"

        user = make_user()
        request = _mock_request()
        db = AsyncMock()
        user_svc = MagicMock()
        user_svc.create_user = AsyncMock(return_value=user)
        email_svc = MagicMock()
        email_svc.send_verification_email = AsyncMock()

        data = RegisterRequest(
            email="test@example.com",
            password="P@ssw0rd!",
            profile=ProfileFields(nickname="nick", firstname="John", lastname="Doe"),
        )

        result = await register_api(request, data, db, user_svc, email_svc)

        assert result.id == str(user.id)
        assert result.email == "test@example.com"
        user_svc.create_user.assert_awaited_once()

    @pytest.mark.asyncio
    @patch(f"{MODULE}.get_current_tenant_id", return_value=None)
    async def test_user_exists_raises(self, mock_tid):
        from auth.api.routes.auth.register import register_api
        from auth.api.schemas.auth import ProfileFields, RegisterRequest

        request = _mock_request()
        db = AsyncMock()
        user_svc = MagicMock()
        user_svc.create_user = AsyncMock(side_effect=ValueError("Email already exists"))
        email_svc = MagicMock()

        data = RegisterRequest(
            email="test@example.com",
            password="P@ssw0rd!",
            profile=ProfileFields(nickname="nick", firstname="John", lastname="Doe"),
        )

        with pytest.raises(HTTPException) as exc_info:
            await register_api(request, data, db, user_svc, email_svc)
        assert exc_info.value.status_code == 400

    @pytest.mark.asyncio
    @patch(f"{MODULE}.settings")
    @patch(f"{MODULE}.get_current_tenant_id", return_value=None)
    async def test_with_registration_source(self, mock_tid, mock_settings):
        from auth.api.routes.auth.register import register_api
        from auth.api.schemas.auth import (
            ProfileFields,
            RegisterRequest,
            RegistrationSource,
        )

        mock_settings.issuer = "https://auth.example.com"

        user = make_user()
        request = _mock_request()
        db = AsyncMock()
        user_svc = MagicMock()
        user_svc.create_user = AsyncMock(return_value=user)
        email_svc = MagicMock()
        email_svc.send_verification_email = AsyncMock()

        data = RegisterRequest(
            email="test@example.com",
            password="P@ssw0rd!",
            profile=ProfileFields(nickname="nick", firstname="John", lastname="Doe"),
            registration_source=RegistrationSource(source="oauth", client_id="c1"),
        )

        result = await register_api(request, data, db, user_svc, email_svc)

        assert result.id == str(user.id)
        call_kwargs = user_svc.create_user.call_args.kwargs
        assert call_kwargs["registration_source"] == "oauth"
        assert call_kwargs["registration_client_id"] == "c1"


class TestGetRegistrationFields:
    @pytest.mark.asyncio
    async def test_no_tenant_returns_defaults(self):
        from auth.api.routes.auth.register import (
            DEFAULT_REGISTRATION_FIELDS,
            get_registration_fields,
        )

        assert await get_registration_fields(AsyncMock(), None) == DEFAULT_REGISTRATION_FIELDS

    @pytest.mark.asyncio
    async def test_tenant_without_settings_returns_defaults(self):
        from auth.api.routes.auth.register import (
            DEFAULT_REGISTRATION_FIELDS,
            get_registration_fields,
        )

        with patch(
            f"{MODULE}.tenant_service.get_settings", new_callable=AsyncMock, return_value=None
        ):
            fields = await get_registration_fields(AsyncMock(), uuid.uuid4())

        assert fields == DEFAULT_REGISTRATION_FIELDS

    @pytest.mark.asyncio
    async def test_non_dict_settings_returns_defaults(self):
        from auth.api.routes.auth.register import (
            DEFAULT_REGISTRATION_FIELDS,
            get_registration_fields,
        )

        with patch(
            f"{MODULE}.tenant_service.get_settings", new_callable=AsyncMock, return_value="oops"
        ):
            fields = await get_registration_fields(AsyncMock(), uuid.uuid4())

        assert fields == DEFAULT_REGISTRATION_FIELDS

    @pytest.mark.asyncio
    async def test_overrides_are_applied(self):
        from auth.api.routes.auth.register import (
            DEFAULT_REGISTRATION_FIELDS,
            get_registration_fields,
        )

        key = next(iter(DEFAULT_REGISTRATION_FIELDS))
        overrides = {"registration_fields": {key: not DEFAULT_REGISTRATION_FIELDS[key]}}

        with patch(
            f"{MODULE}.tenant_service.get_settings", new_callable=AsyncMock, return_value=overrides
        ):
            fields = await get_registration_fields(AsyncMock(), uuid.uuid4())

        assert fields[key] is not DEFAULT_REGISTRATION_FIELDS[key]

    @pytest.mark.asyncio
    async def test_string_tenant_id_is_parsed(self):
        from auth.api.routes.auth.register import (
            DEFAULT_REGISTRATION_FIELDS,
            get_registration_fields,
        )

        tenant_id = uuid.uuid4()
        with patch(
            f"{MODULE}.tenant_service.get_settings", new_callable=AsyncMock, return_value={}
        ) as get_settings:
            fields = await get_registration_fields(AsyncMock(), str(tenant_id))

        assert fields == DEFAULT_REGISTRATION_FIELDS
        assert get_settings.await_args[0][1] == tenant_id


class TestRegisterSubmitNextParam:
    @pytest.mark.asyncio
    @patch(f"{MODULE}.get_current_tenant_id", return_value=None)
    @patch(f"{MODULE}.get_tenant_prefix", return_value="")
    async def test_next_is_preserved_in_verify_redirect(self, mock_prefix, mock_tid):
        from auth.api.routes.auth.register import register_submit

        user_svc = MagicMock()
        user_svc.create_user = AsyncMock(return_value=make_user())
        email_svc = MagicMock()
        email_svc.send_verification_email = AsyncMock()

        fields = {**OPTIONAL_FIELDS, "next": "/dashboard"}
        result = await register_submit(
            _mock_request(),
            "test@example.com",
            "P@ssw0rd!",
            "P@ssw0rd!",
            "nick",
            "John",
            "Doe",
            **fields,
            db=AsyncMock(),
            user_service=user_svc,
            email_service=email_svc,
            branding_service=MagicMock(),
            profile_service=MagicMock(),
        )

        assert result.status_code == 303
        location = result.headers["location"]
        assert "verify-email" in location
        assert "next=%2Fdashboard" in location
