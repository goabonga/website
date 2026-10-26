# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for auth.services.profile — ProfileService."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from auth.services.profile import ProfileData, ProfileService

from tests.conftest import make_execute_result


@pytest.fixture
def db():
    session = AsyncMock()
    session.add = MagicMock()
    return session


@pytest.fixture
def service():
    return ProfileService()


def _make_profile(**kwargs):
    p = MagicMock()
    for k, v in kwargs.items():
        setattr(p, k, v)
    return p


# ── get_profile ──────────────────────────────────────────────────────────────


class TestGetProfile:
    @pytest.mark.asyncio
    async def test_found(self, db, service):
        profile = _make_profile(nickname="test")
        db.execute = AsyncMock(return_value=make_execute_result(scalar_value=profile))
        result = await service.get_profile(db, "user-id")
        assert result is profile

    @pytest.mark.asyncio
    async def test_not_found(self, db, service):
        db.execute = AsyncMock(return_value=make_execute_result(scalar_value=None))
        result = await service.get_profile(db, "user-id")
        assert result is None


# ── get_or_create_profile ────────────────────────────────────────────────────


class TestGetOrCreateProfile:
    @pytest.mark.asyncio
    async def test_existing(self, db, service):
        profile = _make_profile()
        db.execute = AsyncMock(return_value=make_execute_result(scalar_value=profile))
        result = await service.get_or_create_profile(db, "user-id")
        assert result is profile

    @pytest.mark.asyncio
    async def test_create_new(self, db, service):
        service.get_profile = AsyncMock(return_value=None)
        with patch("auth.services.profile.UserProfile") as MockProfile:
            mock_instance = MagicMock()
            MockProfile.return_value = mock_instance
            result = await service.get_or_create_profile(db, "user-id")
        assert result is mock_instance
        db.add.assert_called_once()
        db.flush.assert_called_once()


# ── update_profile ───────────────────────────────────────────────────────────


class TestUpdateProfile:
    @pytest.mark.asyncio
    async def test_update_basic_fields(self, db, service):
        profile = _make_profile(given_name=None, family_name=None)
        service.get_or_create_profile = AsyncMock(return_value=profile)

        data = ProfileData(
            nickname="nick",
            given_name="John",
            family_name="Doe",
            name="John Doe",
            picture_url="https://example.com/pic.jpg",
            website="https://example.com",
            preferred_username="johnd",
            middle_name="M",
            profile_url="https://example.com/profile",
            gender="male",
            birthdate="1990-01-01",
            zoneinfo="UTC",
            locale="en-US",
            phone_number="+1234567890",
        )
        result = await service.update_profile(db, "user-id", data)
        assert result is profile
        db.flush.assert_called_once()

    @pytest.mark.asyncio
    async def test_update_address_fields(self, db, service):
        profile = _make_profile()
        service.get_or_create_profile = AsyncMock(return_value=profile)

        data = ProfileData(
            address_street="123 Main St",
            address_locality="Springfield",
            address_region="IL",
            address_postal_code="62701",
            address_country="US",
        )
        result = await service.update_profile(db, "user-id", data)
        assert result is profile

    @pytest.mark.asyncio
    async def test_auto_generate_name_from_given_family(self, db, service):
        profile = _make_profile(given_name="John", family_name="Doe", name=None)
        service.get_or_create_profile = AsyncMock(return_value=profile)

        # name is None but given_name is set -> should auto-generate
        data = ProfileData(given_name="John", family_name="Doe")
        await service.update_profile(db, "user-id", data)
        assert profile.name == "John Doe"

    @pytest.mark.asyncio
    async def test_auto_generate_name_given_only(self, db, service):
        profile = _make_profile(given_name="John", family_name=None, name=None)
        service.get_or_create_profile = AsyncMock(return_value=profile)

        data = ProfileData(given_name="John")
        await service.update_profile(db, "user-id", data)
        assert profile.name == "John"

    @pytest.mark.asyncio
    async def test_auto_generate_name_family_only(self, db, service):
        profile = _make_profile(given_name=None, family_name="Doe", name=None)
        service.get_or_create_profile = AsyncMock(return_value=profile)

        data = ProfileData(family_name="Doe")
        await service.update_profile(db, "user-id", data)
        assert profile.name == "Doe"

    @pytest.mark.asyncio
    async def test_auto_generate_name_both_none(self, db, service):
        profile = _make_profile(given_name=None, family_name=None, name=None)
        service.get_or_create_profile = AsyncMock(return_value=profile)

        data = ProfileData(given_name="", family_name="")
        await service.update_profile(db, "user-id", data)
        assert profile.name is None

    @pytest.mark.asyncio
    async def test_empty_string_fields_set_to_none(self, db, service):
        profile = _make_profile()
        service.get_or_create_profile = AsyncMock(return_value=profile)

        data = ProfileData(nickname="", website="", phone_number="")
        await service.update_profile(db, "user-id", data)
        assert profile.nickname is None
        assert profile.website is None
        assert profile.phone_number is None

    @pytest.mark.asyncio
    async def test_no_fields_set(self, db, service):
        profile = _make_profile()
        service.get_or_create_profile = AsyncMock(return_value=profile)

        data = ProfileData()  # All None
        await service.update_profile(db, "user-id", data)
        db.flush.assert_called_once()


# ── profile_to_dict ──────────────────────────────────────────────────────────


class TestProfileToDict:
    def test_with_profile(self, service):
        profile = _make_profile(
            nickname="nick",
            name="John Doe",
            given_name="John",
            family_name="Doe",
            middle_name=None,
            preferred_username="johnd",
            picture_url=None,
            profile_url=None,
            website="https://example.com",
            gender="male",
            birthdate="1990-01-01",
            zoneinfo="UTC",
            locale="en-US",
            phone_number=None,
            address_street=None,
            address_locality=None,
            address_region=None,
            address_postal_code=None,
            address_country=None,
        )
        result = service.profile_to_dict(profile)
        assert result["nickname"] == "nick"
        assert result["name"] == "John Doe"
        assert result["given_name"] == "John"
        assert result["website"] == "https://example.com"

    def test_none_profile(self, service):
        result = service.profile_to_dict(None)
        assert all(v is None for v in result.values())
        assert "nickname" in result
        assert "address_country" in result


class TestAddProfile:
    @pytest.mark.asyncio
    async def test_stages_without_commit(self, db, service):
        service._repo.stage = AsyncMock()
        profile = _make_profile()

        result = await service.add_profile(db, profile)

        assert result is profile
        service._repo.stage.assert_awaited_once_with(db, profile)
        db.commit.assert_not_awaited()
