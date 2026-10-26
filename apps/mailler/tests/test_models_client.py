# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for the AuthorizedClient model."""

from mailler.models import AuthorizedClient, Base


class TestAuthorizedClientTable:
    def test_table_registered(self):
        assert "authorized_clients" in Base.metadata.tables

    def test_client_id_is_unique_and_required(self):
        column = AuthorizedClient.__table__.columns["client_id"]
        assert column.unique
        assert column.nullable is False

    def test_columns(self):
        columns = AuthorizedClient.__table__.columns
        for name in (
            "name",
            "is_active",
            "from_email",
            "from_name",
            "reply_to",
            "allowed_senders",
            "allowed_providers",
            "default_provider",
        ):
            assert name in columns

    def test_sender_and_provider_lists_are_required(self):
        columns = AuthorizedClient.__table__.columns
        assert columns["allowed_senders"].nullable is False
        assert columns["allowed_providers"].nullable is False

    def test_repr(self):
        record = AuthorizedClient(client_id="app-one", is_active=False)
        assert repr(record) == "<AuthorizedClient(client_id=app-one, active=False)>"
