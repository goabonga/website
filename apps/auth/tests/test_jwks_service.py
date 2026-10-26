# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for auth.services.jwks — JWKSService (100% mocked)."""

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
from auth.core.security import AESEncryption
from auth.services.jwks import JWKSService
from cryptography.hazmat.primitives.asymmetric import rsa

from tests.conftest import make_jwk


@pytest.fixture
def db():
    session = AsyncMock()
    session.add = MagicMock()
    return session


@pytest.fixture
def encryption():
    key = AESEncryption.generate_key()
    return AESEncryption(key)


@pytest.fixture
def repo():
    """Mock JWKRepository with every public method as an AsyncMock."""
    r = MagicMock()
    r.find_by_id = AsyncMock(return_value=None)
    r.find_by_kid = AsyncMock(return_value=None)
    r.find_active = AsyncMock(return_value=None)
    r.list = AsyncMock(return_value=[])
    r.deactivate_all = AsyncMock()
    r.deactivate_active = AsyncMock()
    r.add = AsyncMock()
    r.delete = AsyncMock()
    return r


@pytest.fixture
def service(encryption, repo):
    return JWKSService(encryption, repository=repo)


# ── generate_key ─────────────────────────────────────────────────────────────


class TestGenerateKey:
    @pytest.mark.asyncio
    async def test_creates_key(self, db, service, repo):
        jwk = await service.generate_key(db, key_size=2048, activate=False)

        assert jwk.kid is not None
        assert jwk.kty == "RSA"
        assert jwk.alg == "RS256"
        assert jwk.use == "sig"
        assert jwk.is_active is False
        assert jwk.public_key_pem.startswith("-----BEGIN PUBLIC KEY-----")
        repo.add.assert_awaited_once()
        db.commit.assert_called_once()
        # No deactivation when not activating
        repo.deactivate_active.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_creates_and_activates(self, db, service, repo):
        jwk = await service.generate_key(db, key_size=2048, activate=True)

        assert jwk.is_active is True
        # Should deactivate existing keys first
        repo.deactivate_active.assert_awaited_once_with(db)
        repo.add.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_private_key_is_encrypted(self, db, service):
        jwk = await service.generate_key(db, key_size=2048)

        assert isinstance(jwk.private_key_encrypted, bytes)
        # Should be decryptable
        private_key = service.decrypt_private_key(jwk)
        assert isinstance(private_key, rsa.RSAPrivateKey)


# ── get_by_id / get_by_kid / legacy aliases ─────────────────────────────────


class TestGetById:
    @pytest.mark.asyncio
    async def test_delegates_to_repo(self, db, service, repo):
        jwk = make_jwk()
        repo.find_by_id = AsyncMock(return_value=jwk)

        result = await service.get_by_id(db, jwk.id)

        assert result is jwk
        repo.find_by_id.assert_awaited_once_with(db, jwk.id)

    @pytest.mark.asyncio
    async def test_not_found(self, db, service, repo):
        repo.find_by_id = AsyncMock(return_value=None)

        result = await service.get_by_id(db, uuid.uuid4())

        assert result is None


class TestGetByKid:
    @pytest.mark.asyncio
    async def test_delegates_to_repo(self, db, service, repo):
        jwk = make_jwk(kid="kid-1")
        repo.find_by_kid = AsyncMock(return_value=jwk)

        result = await service.get_by_kid(db, "kid-1")

        assert result is jwk
        repo.find_by_kid.assert_awaited_once_with(db, "kid-1")

    @pytest.mark.asyncio
    async def test_legacy_alias_get_key_by_kid(self, db, service, repo):
        jwk = make_jwk(kid="kid-1")
        repo.find_by_kid = AsyncMock(return_value=jwk)

        result = await service.get_key_by_kid(db, "kid-1")

        assert result is jwk


class TestGetActiveKey:
    @pytest.mark.asyncio
    async def test_delegates_to_repo(self, db, service, repo):
        jwk = make_jwk(is_active=True)
        repo.find_active = AsyncMock(return_value=jwk)

        result = await service.get_active_key(db)

        assert result is jwk
        repo.find_active.assert_awaited_once_with(db)

    @pytest.mark.asyncio
    async def test_not_found(self, db, service, repo):
        repo.find_active = AsyncMock(return_value=None)

        result = await service.get_active_key(db)

        assert result is None


# ── list / get_all_public_keys ───────────────────────────────────────────────


class TestList:
    @pytest.mark.asyncio
    async def test_list_default(self, db, service, repo):
        jwks = [make_jwk(), make_jwk()]
        repo.list = AsyncMock(return_value=jwks)

        result = await service.list(db)

        assert result == jwks
        repo.list.assert_awaited_once_with(db, include_revoked=False, active_only=False)

    @pytest.mark.asyncio
    async def test_list_include_revoked(self, db, service, repo):
        repo.list = AsyncMock(return_value=[])

        await service.list(db, include_revoked=True)

        repo.list.assert_awaited_once_with(db, include_revoked=True, active_only=False)

    @pytest.mark.asyncio
    async def test_list_active_only(self, db, service, repo):
        repo.list = AsyncMock(return_value=[])

        await service.list(db, active_only=True)

        repo.list.assert_awaited_once_with(db, include_revoked=False, active_only=True)


class TestGetAllPublicKeys:
    @pytest.mark.asyncio
    async def test_returns_non_revoked(self, db, service, repo):
        jwks = [make_jwk(), make_jwk()]
        repo.list = AsyncMock(return_value=jwks)

        result = await service.get_all_public_keys(db)

        assert result == jwks
        repo.list.assert_awaited_once_with(db, include_revoked=False)

    @pytest.mark.asyncio
    async def test_empty(self, db, service, repo):
        repo.list = AsyncMock(return_value=[])

        result = await service.get_all_public_keys(db)

        assert result == []


# ── activate_key ─────────────────────────────────────────────────────────────


class TestActivateKey:
    @pytest.mark.asyncio
    async def test_activates(self, db, service, repo):
        jwk = make_jwk(kid="kid-1", revoked_at=None)
        jwk.is_active = False
        repo.find_by_kid = AsyncMock(return_value=jwk)

        result = await service.activate_key(db, "kid-1")
        assert result is jwk
        assert jwk.is_active is True
        repo.deactivate_all.assert_awaited_once_with(db)
        db.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_not_found(self, db, service, repo):
        repo.find_by_kid = AsyncMock(return_value=None)

        result = await service.activate_key(db, "missing")
        assert result is None
        repo.deactivate_all.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_revoked_key_raises(self, db, service, repo):
        jwk = make_jwk(revoked_at=datetime.now(UTC))
        repo.find_by_kid = AsyncMock(return_value=jwk)

        with pytest.raises(ValueError, match="Cannot activate a revoked key"):
            await service.activate_key(db, jwk.kid)


# ── revoke_key ───────────────────────────────────────────────────────────────


class TestRevokeKey:
    @pytest.mark.asyncio
    async def test_revokes(self, db, service, repo):
        jwk = make_jwk(revoked_at=None)
        jwk.is_active = True
        repo.find_by_kid = AsyncMock(return_value=jwk)

        result = await service.revoke_key(db, jwk.kid)
        assert result is jwk
        assert jwk.is_active is False
        assert jwk.revoked_at is not None
        db.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_not_found(self, db, service, repo):
        repo.find_by_kid = AsyncMock(return_value=None)

        result = await service.revoke_key(db, "missing")
        assert result is None


# ── rotate_keys ──────────────────────────────────────────────────────────────


class TestRotateKeys:
    @pytest.mark.asyncio
    async def test_generates_and_activates(self, db, service, repo):
        jwk = await service.rotate_keys(db, key_size=2048)

        assert jwk.is_active is True
        assert jwk.kid is not None
        repo.deactivate_active.assert_awaited_once_with(db)
        repo.add.assert_awaited_once()


# ── delete / delete_key ──────────────────────────────────────────────────────


class TestDelete:
    @pytest.mark.asyncio
    async def test_deletes_revoked(self, db, service, repo):
        jwk = make_jwk(revoked_at=datetime.now(UTC))
        repo.find_by_kid = AsyncMock(return_value=jwk)

        result = await service.delete(db, jwk.kid)
        assert result is True
        repo.delete.assert_awaited_once_with(db, jwk)
        db.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_not_found(self, db, service, repo):
        repo.find_by_kid = AsyncMock(return_value=None)

        result = await service.delete(db, "missing")
        assert result is False
        repo.delete.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_not_revoked(self, db, service, repo):
        jwk = make_jwk(revoked_at=None)
        repo.find_by_kid = AsyncMock(return_value=jwk)

        result = await service.delete(db, jwk.kid)
        assert result is False
        repo.delete.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_legacy_alias_delete_key(self, db, service, repo):
        jwk = make_jwk(revoked_at=datetime.now(UTC))
        repo.find_by_kid = AsyncMock(return_value=jwk)

        result = await service.delete_key(db, jwk.kid)
        assert result is True


# ── decrypt_private_key ──────────────────────────────────────────────────────


class TestDecryptPrivateKey:
    @pytest.mark.asyncio
    async def test_roundtrip(self, db, service):
        jwk = await service.generate_key(db, key_size=2048)

        private_key = service.decrypt_private_key(jwk)
        assert isinstance(private_key, rsa.RSAPrivateKey)

        # Verify it can sign
        from cryptography.hazmat.primitives import hashes
        from cryptography.hazmat.primitives.asymmetric import padding

        signature = private_key.sign(
            b"test data",
            padding.PKCS1v15(),
            hashes.SHA256(),
        )
        assert len(signature) > 0


# ── to_jwk_public ───────────────────────────────────────────────────────────


class TestToJwkPublic:
    @pytest.mark.asyncio
    async def test_format(self, db, service):
        jwk = await service.generate_key(db, key_size=2048)

        public = service.to_jwk_public(jwk)

        assert public["kty"] == "RSA"
        assert public["use"] == "sig"
        assert public["alg"] == "RS256"
        assert public["kid"] == jwk.kid
        assert "n" in public  # modulus
        assert "e" in public  # exponent
        # Base64url: no padding chars
        assert "=" not in public["n"]
        assert "=" not in public["e"]


# ── default repository ───────────────────────────────────────────────────────


class TestDefaultRepository:
    def test_uses_default_repo_when_not_injected(self, encryption):
        """Service must create a default JWKRepository when none is supplied."""
        from auth.db.repositories.jwk import JWKRepository

        service = JWKSService(encryption)
        assert isinstance(service._repo, JWKRepository)
