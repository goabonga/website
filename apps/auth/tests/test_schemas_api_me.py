# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for auth.api.schemas.api.me.schemas — request/response validation."""

import pytest
from auth.api.schemas.api.me.schemas import PasswordChangeRequest
from pydantic import ValidationError


class TestPasswordChangeRequest:
    def test_accepts_a_strong_password(self):
        req = PasswordChangeRequest(current_password="old", new_password="Str0ngPass")

        assert req.new_password == "Str0ngPass"

    @pytest.mark.parametrize(
        ("password", "message"),
        [
            ("Sh0rt", "at least 8 characters"),
            ("nouppercase1", "one uppercase letter"),
            ("NOLOWERCASE1", "one lowercase letter"),
            ("NoDigitsHere", "one digit"),
        ],
    )
    def test_rejects_weak_passwords(self, password, message):
        with pytest.raises(ValidationError, match=message):
            PasswordChangeRequest(current_password="old", new_password=password)
