# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""User model built from JWT claims."""

from uuid import UUID

import pytest
from apt_server.auth.models import User

USER_ID = "3f2c8f0e-1b7a-4b43-9a55-0d2f4f0e9a11"


def test_user_token_with_uuid_subject() -> None:
    user = User.from_jwt_claims(
        {"sub": USER_ID, "email": "a@example.com", "name": "Alice", "scope": "apt:read openid"}
    )

    assert user.id == UUID(USER_ID)
    assert user.email == "a@example.com"
    assert user.name == "Alice"
    assert user.scopes == ["apt:read", "openid"]
    assert user.is_machine_client is False


def test_machine_token_when_client_id_equals_subject() -> None:
    user = User.from_jwt_claims({"sub": "ci-bot", "client_id": "ci-bot"})

    assert user.is_machine_client is True
    assert user.id == "ci-bot"
    assert user.client_id == "ci-bot"


def test_machine_token_when_subject_is_not_a_uuid() -> None:
    user = User.from_jwt_claims({"sub": "not-a-uuid"})

    assert user.is_machine_client is True
    assert user.id == "not-a-uuid"


def test_missing_subject_is_rejected() -> None:
    with pytest.raises(ValueError, match="sub"):
        User.from_jwt_claims({"scope": "apt:read"})


@pytest.mark.parametrize(
    ("claims", "expected"),
    [
        ({"scope": "a b"}, ["a", "b"]),
        ({"scope": ""}, []),
        ({"scp": ["a", "b"]}, ["a", "b"]),
        ({"scope": 12}, []),
        ({}, []),
    ],
)
def test_scope_claim_formats(claims: dict, expected: list[str]) -> None:
    assert User.from_jwt_claims({"sub": USER_ID, **claims}).scopes == expected


def test_name_falls_back_to_preferred_username() -> None:
    user = User.from_jwt_claims({"sub": USER_ID, "preferred_username": "alice"})

    assert user.name == "alice"


@pytest.mark.parametrize(
    ("scopes", "wanted", "granted"),
    [
        (["apt:read"], "apt:read", True),
        (["apt:read"], "apt:write", False),
        (["*"], "anything", True),
        (["apt:*"], "apt:write:main", True),
        (["apt:*"], "vpn:read", False),
        ([], "apt:read", False),
    ],
)
def test_has_scope_supports_wildcards(scopes: list[str], wanted: str, granted: bool) -> None:
    user = User(id="u", scopes=scopes)

    assert user.has_scope(wanted) is granted


def test_has_any_and_all_scopes() -> None:
    user = User(id="u", scopes=["a", "b"])

    assert user.has_any_scope(["x", "a"])
    assert not user.has_any_scope(["x", "y"])
    assert user.has_all_scopes(["a", "b"])
    assert not user.has_all_scopes(["a", "c"])
