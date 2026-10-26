# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for auth.services.email — EmailService."""

import hashlib
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from auth.services.email import EmailService, generate_verification_code, hash_code

from tests.conftest import make_execute_result


@pytest.fixture
def db():
    session = AsyncMock()
    session.add = MagicMock()
    return session


@pytest.fixture
def service():
    return EmailService()


# ── Helper functions ─────────────────────────────────────────────────────────


class TestGenerateVerificationCode:
    def test_length(self):
        code = generate_verification_code()
        assert len(code) == 6

    def test_digits_only(self):
        code = generate_verification_code()
        assert code.isdigit()

    def test_randomness(self):
        codes = {generate_verification_code() for _ in range(50)}
        assert len(codes) > 1


class TestHashCode:
    def test_sha256(self):
        expected = hashlib.sha256(b"123456").hexdigest()
        assert hash_code("123456") == expected


# ── send_email ───────────────────────────────────────────────────────────────


class TestSendEmail:
    @pytest.mark.asyncio
    async def test_success(self, service):
        with patch("auth.services.email.send_email_task") as mock_task:
            result = await service.send_email("test@example.com", "Subject", "<p>HTML</p>", "Text")
        assert result is True
        mock_task.delay.assert_called_once()

    @pytest.mark.asyncio
    async def test_failure(self, service):
        with patch("auth.services.email.send_email_task") as mock_task:
            mock_task.delay.side_effect = Exception("Celery down")
            result = await service.send_email("test@example.com", "Subject", "<p>HTML</p>")
        assert result is False


# ── create_verification_code ─────────────────────────────────────────────────


class TestCreateVerificationCode:
    @pytest.mark.asyncio
    async def test_success_with_string_user_id(self, db, service):
        with (
            patch("auth.services.email.VerificationCode"),
            patch("auth.services.email.settings") as mock_settings,
        ):
            mock_settings.verification_code_expiry_hours = 24
            code = await service.create_verification_code(
                db, "550e8400-e29b-41d4-a716-446655440000", "test@example.com"
            )
        assert len(code) == 6
        assert code.isdigit()
        db.add.assert_called_once()
        db.flush.assert_called_once()

    @pytest.mark.asyncio
    async def test_success_with_uuid_user_id(self, db, service):
        import uuid

        with (
            patch("auth.services.email.VerificationCode"),
            patch("auth.services.email.settings") as mock_settings,
        ):
            mock_settings.verification_code_expiry_hours = 24
            code = await service.create_verification_code(db, uuid.uuid4(), "test@example.com")
        assert len(code) == 6


# ── has_valid_verification_code ──────────────────────────────────────────────


class TestHasValidVerificationCode:
    @pytest.mark.asyncio
    async def test_has_valid(self, db, service):
        vc = MagicMock()
        db.execute = AsyncMock(return_value=make_execute_result(scalar_value=vc))
        result = await service.has_valid_verification_code(db, "test@example.com")
        assert result is True

    @pytest.mark.asyncio
    async def test_no_valid(self, db, service):
        db.execute = AsyncMock(return_value=make_execute_result(scalar_value=None))
        result = await service.has_valid_verification_code(db, "test@example.com")
        assert result is False


# ── verify_code ──────────────────────────────────────────────────────────────


class TestVerifyCode:
    @pytest.mark.asyncio
    async def test_valid_code_with_email(self, db, service):
        vc = MagicMock()
        vc.used_at = None
        ue = MagicMock()
        ue.user_id = "user-1"

        db.execute = AsyncMock(
            side_effect=[
                make_execute_result(scalar_value=vc),  # find verification code
                make_execute_result(scalar_value=ue),  # find user email
            ]
        )
        result = await service.verify_code(db, "test@example.com", "123456")
        assert result is True
        assert vc.used_at is not None
        assert ue.is_verified is True
        db.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_valid_code_no_email(self, db, service):
        vc = MagicMock()
        vc.used_at = None

        db.execute = AsyncMock(
            side_effect=[
                make_execute_result(scalar_value=vc),
                make_execute_result(scalar_value=None),
            ]
        )
        result = await service.verify_code(db, "test@example.com", "123456")
        assert result is True
        db.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_invalid_code(self, db, service):
        db.execute = AsyncMock(return_value=make_execute_result(scalar_value=None))
        result = await service.verify_code(db, "test@example.com", "000000")
        assert result is False


# ── send_verification_email ──────────────────────────────────────────────────


class TestSendVerificationEmail:
    @pytest.mark.asyncio
    async def test_success_with_base_url(self, db, service):
        service.create_verification_code = AsyncMock(return_value="123456")
        service.send_email = AsyncMock(return_value=True)

        mock_renderer = MagicMock()
        mock_renderer.render_email_for_tenant = AsyncMock(return_value=("<html>", "text"))
        with (
            patch("auth.services.email_renderer.get_email_renderer", return_value=mock_renderer),
            patch("auth.services.email.settings") as mock_settings,
        ):
            mock_settings.verification_code_expiry_hours = 24
            result = await service.send_verification_email(
                db,
                "user-1",
                "test@example.com",
                base_url="https://auth.example.com",
                branding=None,
                tenant_id="tenant-1",
            )
        assert result is True

    @pytest.mark.asyncio
    async def test_success_without_base_url(self, db, service):
        service.create_verification_code = AsyncMock(return_value="123456")
        service.send_email = AsyncMock(return_value=True)

        mock_renderer = MagicMock()
        mock_renderer.render_email_for_tenant = AsyncMock(return_value=("<html>", "text"))
        with (
            patch("auth.services.email_renderer.get_email_renderer", return_value=mock_renderer),
            patch("auth.services.email.settings") as mock_settings,
        ):
            mock_settings.verification_code_expiry_hours = 24
            result = await service.send_verification_email(
                db,
                "user-1",
                "test@example.com",
            )
        assert result is True

    @pytest.mark.asyncio
    async def test_send_fails(self, db, service):
        service.create_verification_code = AsyncMock(return_value="123456")
        service.send_email = AsyncMock(return_value=False)

        mock_renderer = MagicMock()
        mock_renderer.render_email_for_tenant = AsyncMock(return_value=("<html>", "text"))
        with (
            patch("auth.services.email_renderer.get_email_renderer", return_value=mock_renderer),
            patch("auth.services.email.settings") as mock_settings,
        ):
            mock_settings.verification_code_expiry_hours = 24
            result = await service.send_verification_email(
                db,
                "user-1",
                "test@example.com",
            )
        assert result is False

    @pytest.mark.asyncio
    async def test_exception_returns_false(self, db, service):
        service.create_verification_code = AsyncMock(side_effect=Exception("unexpected"))
        result = await service.send_verification_email(
            db,
            "user-1",
            "test@example.com",
        )
        assert result is False
