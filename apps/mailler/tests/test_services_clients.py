# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for the authorized clients service: the gate and the identity rules."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException
from mailler.models.client import AuthorizedClient
from mailler.services import clients as service
from mailler.services.clients import (
    check_overrides,
    clear_cache,
    ensure_authorized,
    get_client,
    resolve_identity,
)


def _client(**fields) -> AuthorizedClient:
    values = {
        "client_id": "app-one",
        "is_active": True,
        "from_email": "app@one.example",
        "from_name": "App One",
        "reply_to": None,
        "allowed_senders": [{"email": "alerts@one.example", "name": "Alerts"}],
        "allowed_providers": ["ses"],
        "default_provider": "brevo",
    }
    values.update(fields)
    return AuthorizedClient(**values)


# ---------------------------------------------------------------------------
# get_client
# ---------------------------------------------------------------------------


class TestGetClient:
    async def test_without_client_id(self):
        db = AsyncMock()
        assert await get_client(db, None) is None
        db.execute.assert_not_called()

    async def test_queries_the_registry(self):
        db = AsyncMock()
        result = MagicMock()
        result.scalar_one_or_none.return_value = "record"
        db.execute.return_value = result

        assert await get_client(db, "app-one") == "record"
        assert db.execute.await_args.args[0].compile().params["client_id_1"] == "app-one"


# ---------------------------------------------------------------------------
# ensure_authorized
# ---------------------------------------------------------------------------


@pytest.fixture
def registry_session():
    """Replace the session factory of the gate; ``set_state`` chooses what the registry holds."""
    session = AsyncMock()
    result = MagicMock()
    session.execute.return_value = result
    factory = MagicMock()
    factory.return_value.__aenter__ = AsyncMock(return_value=session)
    factory.return_value.__aexit__ = AsyncMock(return_value=False)

    def set_state(value):
        result.scalar_one_or_none.return_value = value

    clear_cache()
    with patch.object(service, "AsyncSessionLocal", factory):
        yield session, set_state
    clear_cache()


class TestEnsureAuthorized:
    async def test_active_client_passes(self, registry_session):
        _, set_state = registry_session
        set_state(True)
        await ensure_authorized("app-one")

    async def test_unregistered_client_is_refused(self, registry_session):
        _, set_state = registry_session
        set_state(None)
        with pytest.raises(HTTPException) as exc_info:
            await ensure_authorized("app-one")
        assert exc_info.value.status_code == 403
        assert exc_info.value.detail == "Client is not registered"

    async def test_inactive_client_is_refused(self, registry_session):
        _, set_state = registry_session
        set_state(False)
        with pytest.raises(HTTPException) as exc_info:
            await ensure_authorized("app-one")
        assert exc_info.value.status_code == 403
        assert exc_info.value.detail == "Client is deactivated"

    async def test_active_client_is_remembered(self, registry_session):
        session, set_state = registry_session
        set_state(True)
        with patch.object(service.settings, "client_cache_ttl", 60):
            await ensure_authorized("app-one")
            await ensure_authorized("app-one")
        assert session.execute.await_count == 1

    async def test_cache_can_be_disabled(self, registry_session):
        session, set_state = registry_session
        set_state(True)
        with patch.object(service.settings, "client_cache_ttl", 0):
            await ensure_authorized("app-one")
            await ensure_authorized("app-one")
        assert session.execute.await_count == 2

    async def test_cache_expires(self, registry_session):
        session, set_state = registry_session
        set_state(True)
        with (
            patch.object(service.settings, "client_cache_ttl", 60),
            patch.object(service.time, "monotonic", side_effect=[100.0, 200.0, 200.0]),
        ):
            await ensure_authorized("app-one")
            await ensure_authorized("app-one")
        assert session.execute.await_count == 2

    async def test_refusals_are_not_remembered(self, registry_session):
        session, set_state = registry_session
        set_state(None)
        with patch.object(service.settings, "client_cache_ttl", 60):
            for _ in range(2):
                with pytest.raises(HTTPException):
                    await ensure_authorized("app-one")
        assert session.execute.await_count == 2

    async def test_clear_cache_forgets_clients(self, registry_session):
        session, set_state = registry_session
        set_state(True)
        with patch.object(service.settings, "client_cache_ttl", 60):
            await ensure_authorized("app-one")
            clear_cache()
            await ensure_authorized("app-one")
        assert session.execute.await_count == 2


# ---------------------------------------------------------------------------
# check_overrides
# ---------------------------------------------------------------------------


def _forbidden(**kwargs):
    with pytest.raises(HTTPException) as exc_info:
        check_overrides(kwargs.pop("client", _client()), is_admin=False, **kwargs)
    assert exc_info.value.status_code == 403
    return exc_info.value.detail


class TestCheckOverrides:
    def test_nothing_requested_is_fine(self):
        check_overrides(_client(), is_admin=False)

    def test_default_sender_is_allowed(self):
        check_overrides(
            _client(), is_admin=False, from_email="app@one.example", from_name="App One"
        )

    def test_sender_comparison_ignores_case(self):
        check_overrides(_client(), is_admin=False, from_email="APP@One.Example")

    def test_other_allowed_sender_with_its_name(self):
        check_overrides(
            _client(), is_admin=False, from_email="alerts@one.example", from_name="Alerts"
        )

    def test_unknown_sender_is_refused(self):
        assert "Sender address" in _forbidden(from_email="boss@bank.example")

    def test_sender_name_of_another_identity_is_refused(self):
        assert "Sender name" in _forbidden(from_email="alerts@one.example", from_name="App One")

    def test_arbitrary_sender_name_is_refused(self):
        assert "Sender name" in _forbidden(from_name="The Bank")

    def test_default_sender_name_alone_is_allowed(self):
        check_overrides(_client(), is_admin=False, from_name="App One")

    def test_fixed_reply_to_cannot_be_changed(self):
        client = _client(reply_to="support@one.example")
        assert "Reply-to" in _forbidden(client=client, reply_to="phish@evil.example")
        check_overrides(client, is_admin=False, reply_to="Support@One.example")

    def test_free_reply_to_when_the_client_has_none(self):
        check_overrides(_client(reply_to=None), is_admin=False, reply_to="anyone@one.example")

    def test_default_and_allowed_providers(self):
        check_overrides(_client(), is_admin=False, provider="brevo")
        check_overrides(_client(), is_admin=False, provider="ses")

    def test_other_provider_is_refused(self):
        assert "Provider" in _forbidden(provider="sendgrid")

    def test_client_without_providers_is_refused(self):
        client = _client(allowed_providers=[], default_provider=None)
        assert "Provider" in _forbidden(client=client, provider="brevo")

    def test_unregistered_client_is_refused(self):
        assert "not registered" in _forbidden(client=None)

    def test_administrators_are_not_checked(self):
        check_overrides(
            None,
            is_admin=True,
            from_email="anyone@anywhere.example",
            from_name="Anyone",
            reply_to="x@y.example",
            provider="whatever",
        )


# ---------------------------------------------------------------------------
# resolve_identity
# ---------------------------------------------------------------------------


class TestResolveIdentity:
    def test_defaults_come_from_the_record(self):
        identity = resolve_identity(_client(reply_to="support@one.example"), is_admin=False)
        assert identity.from_email == "app@one.example"
        assert identity.from_name == "App One"
        assert identity.reply_to == "support@one.example"
        assert identity.provider == "brevo"

    def test_chosen_identity_brings_its_name(self):
        identity = resolve_identity(_client(), is_admin=False, from_email="alerts@one.example")
        assert (identity.from_email, identity.from_name) == ("alerts@one.example", "Alerts")

    def test_chosen_provider(self):
        assert resolve_identity(_client(), is_admin=False, provider="ses").provider == "ses"

    def test_free_reply_to_is_kept(self):
        identity = resolve_identity(_client(), is_admin=False, reply_to="me@one.example")
        assert identity.reply_to == "me@one.example"

    def test_forbidden_values_are_refused(self):
        with pytest.raises(HTTPException) as exc_info:
            resolve_identity(_client(), is_admin=False, from_email="boss@bank.example")
        assert exc_info.value.status_code == 403

    def test_client_without_sender_gets_422_and_no_platform_fallback(self):
        with (
            patch.object(service.settings, "default_from", "platform@example.test"),
            pytest.raises(HTTPException) as exc_info,
        ):
            resolve_identity(_client(from_email=None), is_admin=False)
        assert exc_info.value.status_code == 422
        assert "No sender address" in exc_info.value.detail

    def test_client_without_provider_gets_422_and_no_platform_fallback(self):
        with (
            patch.object(service.settings, "default_provider", "platform-provider"),
            pytest.raises(HTTPException) as exc_info,
        ):
            resolve_identity(_client(default_provider=None), is_admin=False)
        assert exc_info.value.status_code == 422
        assert "No provider" in exc_info.value.detail

    def test_administrator_values_are_taken_as_they_are(self):
        identity = resolve_identity(
            None,
            is_admin=True,
            from_email="ops@platform.example",
            from_name="Ops",
            reply_to="r@platform.example",
            provider="ses",
        )
        assert identity.from_email == "ops@platform.example"
        assert identity.provider == "ses"

    def test_administrator_falls_back_to_the_platform_settings(self):
        with (
            patch.object(service.settings, "default_from", "platform@example.test"),
            patch.object(service.settings, "default_from_name", "Platform"),
            patch.object(service.settings, "default_provider", "platform-provider"),
        ):
            identity = resolve_identity(None, is_admin=True)
        assert identity.from_email == "platform@example.test"
        assert identity.from_name == "Platform"
        assert identity.provider == "platform-provider"

    def test_administrator_without_anything_gets_422(self):
        with (
            patch.object(service.settings, "default_from", ""),
            patch.object(service.settings, "default_provider", ""),
        ):
            with pytest.raises(HTTPException) as exc_info:
                resolve_identity(None, is_admin=True, provider="ses")
            assert exc_info.value.status_code == 422
            with pytest.raises(HTTPException) as exc_info:
                resolve_identity(None, is_admin=True, from_email="ops@platform.example")
            assert exc_info.value.status_code == 422

    def test_administrator_with_a_record_uses_it_before_the_platform(self):
        with patch.object(service.settings, "default_from", "platform@example.test"):
            identity = resolve_identity(_client(), is_admin=True)
        assert identity.from_email == "app@one.example"
