# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Branch coverage for auth.api.routes.auth.settings.

The happy paths live in ``test_routes_auth_settings.py``; this module fills in
the guard clauses and helper branches those tests do not reach.
"""

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

MODULE = "auth.api.routes.auth.settings"

pytestmark = pytest.mark.asyncio


def _request(cookies=None, query_params=None, form_data=None, path="/auth/settings"):
    request = MagicMock()
    request.cookies = cookies if cookies is not None else {"session": "tok"}
    request.query_params = query_params or {}
    request.headers = {}
    url = MagicMock()
    url.scheme = "https"
    url.netloc = "auth.example.com"
    url.path = path
    url.query = ""
    request.url = url
    request.base_url = "https://auth.example.com/"
    if form_data is not None:
        form = MagicMock()
        form.get = lambda key, default="": form_data.get(key, default)
        form.items = lambda: form_data.items()
        form.getlist = lambda key: form_data.get(key, [])
        request.form = AsyncMock(return_value=form)
    else:
        request.form = AsyncMock(return_value=MagicMock())
    return request


def _session_service(user=None):
    service = AsyncMock()
    service.get_user_by_session_token = AsyncMock(return_value=user)
    return service


# ---------------------------------------------------------------------------
# get_profile_fields
# ---------------------------------------------------------------------------


class TestGetProfileFields:
    async def test_no_tenant_returns_defaults(self):
        from auth.api.routes.auth.settings import DEFAULT_PROFILE_FIELDS, get_profile_fields

        assert await get_profile_fields(AsyncMock(), None) == DEFAULT_PROFILE_FIELDS

    async def test_missing_settings_returns_defaults(self):
        from auth.api.routes.auth.settings import DEFAULT_PROFILE_FIELDS, get_profile_fields

        with patch(f"{MODULE}.tenant_service.get_settings", AsyncMock(return_value=None)):
            assert await get_profile_fields(AsyncMock(), uuid.uuid4()) == DEFAULT_PROFILE_FIELDS

    async def test_non_dict_settings_returns_defaults(self):
        from auth.api.routes.auth.settings import DEFAULT_PROFILE_FIELDS, get_profile_fields

        with patch(f"{MODULE}.tenant_service.get_settings", AsyncMock(return_value="oops")):
            assert await get_profile_fields(AsyncMock(), uuid.uuid4()) == DEFAULT_PROFILE_FIELDS

    async def test_overrides_are_applied(self):
        from auth.api.routes.auth.settings import DEFAULT_PROFILE_FIELDS, get_profile_fields

        key = next(iter(DEFAULT_PROFILE_FIELDS))
        overrides = {"profile_fields": {key: not DEFAULT_PROFILE_FIELDS[key]}}

        with patch(f"{MODULE}.tenant_service.get_settings", AsyncMock(return_value=overrides)):
            fields = await get_profile_fields(AsyncMock(), uuid.uuid4())

        assert fields[key] is not DEFAULT_PROFILE_FIELDS[key]

    async def test_string_tenant_id_is_parsed(self):
        from auth.api.routes.auth.settings import get_profile_fields

        tenant_id = uuid.uuid4()

        with patch(
            f"{MODULE}.tenant_service.get_settings", AsyncMock(return_value={})
        ) as get_settings:
            await get_profile_fields(AsyncMock(), str(tenant_id))

        assert get_settings.await_args[0][1] == tenant_id


# ---------------------------------------------------------------------------
# get_branding_for_request
# ---------------------------------------------------------------------------


class TestGetBrandingForRequestUuidContext:
    async def test_uuid_tenant_id_is_used_directly(self):
        from auth.api.routes.auth.settings import get_branding_for_request

        tenant_id = uuid.uuid4()
        ctx = MagicMock()
        ctx.tenant_id = tenant_id
        service = MagicMock()
        service.get_branding = AsyncMock(return_value="cfg")

        with (
            patch(f"{MODULE}.get_tenant_context", return_value=ctx),
            patch(f"{MODULE}.BrandingService", return_value=service),
        ):
            result = await get_branding_for_request(AsyncMock())

        assert result == "cfg"
        assert service.get_branding.await_args[0][1] == tenant_id


# ---------------------------------------------------------------------------
# The "session cookie present but no longer valid" guard
# ---------------------------------------------------------------------------


def _handler_calls():
    """(name, kwargs-builder) pairs for every handler guarding on a stale session."""
    return [
        (
            "settings_profile_update",
            lambda s: {
                "request": _request(),
                "db": AsyncMock(),
                "session_service": s,
                "profile_service": AsyncMock(),
                "branding_service": AsyncMock(),
            },
        ),
        (
            "settings_upload_avatar",
            lambda s: {
                "request": _request(),
                "db": AsyncMock(),
                "session_service": s,
                "profile_service": AsyncMock(),
                "avatar": MagicMock(),
            },
        ),
        (
            "settings_password",
            lambda s: {
                "request": _request(),
                "db": AsyncMock(),
                "session_service": s,
                "branding_service": AsyncMock(),
            },
        ),
        (
            "settings_password_update",
            lambda s: {
                "request": _request(),
                "db": AsyncMock(),
                "session_service": s,
                "password_service": AsyncMock(),
                "branding_service": AsyncMock(),
                "current_password": "old",
                "new_password": "New1!aaa",
                "confirm_password": "New1!aaa",
            },
        ),
        (
            "settings_security",
            lambda s: {
                "request": _request(),
                "db": AsyncMock(),
                "session_service": s,
                "mfa_service": AsyncMock(),
                "branding_service": AsyncMock(),
            },
        ),
        (
            "settings_sessions",
            lambda s: {
                "request": _request(),
                "db": AsyncMock(),
                "session_service": s,
                "branding_service": AsyncMock(),
            },
        ),
        (
            "settings_revoke_session",
            lambda s: {
                "request": _request(),
                "session_id": str(uuid.uuid4()),
                "db": AsyncMock(),
                "session_service": s,
                "branding_service": AsyncMock(),
            },
        ),
        (
            "settings_revoke_all_sessions",
            lambda s: {
                "request": _request(),
                "db": AsyncMock(),
                "session_service": s,
                "branding_service": AsyncMock(),
            },
        ),
        (
            "settings_applications",
            lambda s: {
                "request": _request(),
                "db": AsyncMock(),
                "session_service": s,
                "token_service": AsyncMock(),
                "branding_service": AsyncMock(),
            },
        ),
        (
            "settings_revoke_application",
            lambda s: {
                "request": _request(),
                "client_id": "client-1",
                "db": AsyncMock(),
                "session_service": s,
                "token_service": AsyncMock(),
                "branding_service": AsyncMock(),
            },
        ),
        (
            "settings_emails",
            lambda s: {
                "request": _request(),
                "db": AsyncMock(),
                "session_service": s,
                "email_service": AsyncMock(),
                "branding_service": AsyncMock(),
            },
        ),
        (
            "settings_add_email",
            lambda s: {
                "request": _request(),
                "db": AsyncMock(),
                "session_service": s,
                "email_service": AsyncMock(),
                "email": "new@example.com",
            },
        ),
        (
            "settings_remove_email",
            lambda s: {
                "request": _request(),
                "email_id": str(uuid.uuid4()),
                "db": AsyncMock(),
                "session_service": s,
            },
        ),
        (
            "settings_set_primary_email",
            lambda s: {
                "request": _request(),
                "email_id": str(uuid.uuid4()),
                "db": AsyncMock(),
                "session_service": s,
            },
        ),
        (
            "settings_verify_email",
            lambda s: {
                "request": _request(),
                "email_id": str(uuid.uuid4()),
                "code": "123456",
                "db": AsyncMock(),
                "session_service": s,
                "email_service": AsyncMock(),
            },
        ),
        (
            "settings_resend_email_verification",
            lambda s: {
                "request": _request(),
                "email_id": str(uuid.uuid4()),
                "db": AsyncMock(),
                "session_service": s,
                "email_service": AsyncMock(),
            },
        ),
        (
            "settings_tenants",
            lambda s: {
                "request": _request(),
                "db": AsyncMock(),
                "session_service": s,
                "branding_service": AsyncMock(),
            },
        ),
    ]


@pytest.mark.parametrize(
    ("name", "build_kwargs"), _handler_calls(), ids=lambda v: v if isinstance(v, str) else ""
)
class TestStaleSessionRedirects:
    async def test_stale_cookie_redirects_to_login(self, name, build_kwargs):
        import auth.api.routes.auth.settings as settings_module

        handler = getattr(settings_module, name)

        with patch(f"{MODULE}.get_session_cookie_name", return_value="session"):
            result = await handler(**build_kwargs(_session_service(user=None)))

        assert result.status_code in (302, 303)
        assert "/auth/login" in result.headers["location"]


# ---------------------------------------------------------------------------
# Email lookup loops
# ---------------------------------------------------------------------------


def _user_with_emails(*emails):
    user = MagicMock()
    user.id = uuid.uuid4()
    user.emails = list(emails)
    return user


def _email(email="a@example.com", is_primary=False, is_verified=False):
    row = MagicMock()
    row.id = uuid.uuid4()
    row.email = email
    row.is_primary = is_primary
    row.is_verified = is_verified
    return row


class TestEmailLookupSkipsNonMatchingRows:
    async def test_verify_email_scans_past_other_addresses(self):
        from auth.api.routes.auth.settings import settings_verify_email

        other, target = _email("other@example.com"), _email("target@example.com")
        user = _user_with_emails(other, target)
        email_service = AsyncMock()
        email_service.verify_code = AsyncMock(return_value=True)

        with patch(f"{MODULE}.get_session_cookie_name", return_value="session"):
            result = await settings_verify_email(
                request=_request(),
                email_id=str(target.id),
                code="123456",
                db=AsyncMock(),
                session_service=_session_service(user),
                email_service=email_service,
            )

        assert result.status_code == 303
        email_service.verify_code.assert_awaited_once()

    async def test_resend_verification_scans_past_other_addresses(self):
        from auth.api.routes.auth.settings import settings_resend_email_verification

        other, target = _email("other@example.com"), _email("target@example.com")
        user = _user_with_emails(other, target)
        email_service = AsyncMock()
        email_service.send_verification_email = AsyncMock(return_value=True)

        with patch(f"{MODULE}.get_session_cookie_name", return_value="session"):
            result = await settings_resend_email_verification(
                request=_request(),
                email_id=str(target.id),
                db=AsyncMock(),
                session_service=_session_service(user),
                email_service=email_service,
            )

        assert result.status_code == 303
