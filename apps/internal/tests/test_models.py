# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for the authentication and database models."""

import uuid

import pytest
from internal.auth.models import User


class TestUserFromJwtClaims:
    def test_from_jwt_claims(self):
        claims = {
            "sub": "12345678-1234-5678-1234-567812345678",
            "email": "user@example.com",
            "name": "Test User",
            "scope": "knowledge:read prompts:write",
        }
        user = User.from_jwt_claims(claims)
        assert user.id == uuid.UUID("12345678-1234-5678-1234-567812345678")
        assert user.email == "user@example.com"
        assert user.name == "Test User"
        assert user.scopes == ["knowledge:read", "prompts:write"]

    def test_from_jwt_claims_preferred_username(self):
        claims = {
            "sub": "12345678-1234-5678-1234-567812345678",
            "preferred_username": "testuser",
            "scope": "",
        }
        user = User.from_jwt_claims(claims)
        assert user.name == "testuser"
        assert user.scopes == []

    def test_from_jwt_claims_missing_sub(self):
        with pytest.raises(ValueError, match="JWT missing 'sub' claim"):
            User.from_jwt_claims({"email": "user@example.com"})

    def test_from_jwt_claims_empty_scope(self):
        claims = {"sub": "12345678-1234-5678-1234-567812345678"}
        user = User.from_jwt_claims(claims)
        assert user.scopes == []


class TestUserHasScope:
    def test_exact_match(self, mock_user):
        assert mock_user.has_scope("knowledge:read") is True
        assert mock_user.has_scope("knowledge:delete") is False

    def test_wildcard_star(self, mock_admin_user):
        assert mock_admin_user.has_scope("anything:read") is True
        assert mock_admin_user.has_scope("whatever") is True

    def test_resource_wildcard(self):
        user = User(id=uuid.uuid4(), scopes=["knowledge:*"])
        assert user.has_scope("knowledge:read") is True
        assert user.has_scope("knowledge:write") is True
        assert user.has_scope("knowledge:delete") is True
        assert user.has_scope("prompts:read") is False

    def test_internal_wildcard(self):
        user = User(id=uuid.uuid4(), scopes=["internal:*"])
        assert user.has_scope("namespaces:read") is True
        assert user.has_scope("prompts:write") is True
        assert user.has_scope("knowledge:delete") is True
        assert user.has_scope("conversations:read") is True

    def test_internal_wildcard_non_internal_resource(self):
        user = User(id=uuid.uuid4(), scopes=["internal:*"])
        assert user.has_scope("users:read") is False
        assert user.has_scope("billing:write") is False

    def test_no_scopes(self):
        user = User(id=uuid.uuid4(), scopes=[])
        assert user.has_scope("knowledge:read") is False


class TestUserScopeHelpers:
    def test_has_any_scope(self, mock_user):
        assert mock_user.has_any_scope(["knowledge:read", "users:admin"]) is True
        assert mock_user.has_any_scope(["users:admin", "billing:read"]) is False

    def test_has_all_scopes(self, mock_user):
        assert mock_user.has_all_scopes(["knowledge:read", "prompts:read"]) is True
        assert mock_user.has_all_scopes(["knowledge:read", "users:admin"]) is False

    def test_can_write(self, mock_user):
        assert mock_user.can_write("knowledge") is True
        assert mock_user.can_write("prompts") is False

    def test_can_delete(self, mock_user):
        assert mock_user.can_delete("knowledge") is False

    def test_admin_can_write_and_delete(self, mock_admin_user):
        assert mock_admin_user.can_write("anything") is True
        assert mock_admin_user.can_delete("anything") is True


class TestContactProperties:
    """Test Contact computed properties without database.

    Uses SimpleNamespace + property.fget to avoid SQLAlchemy instrumentation.
    """

    def test_full_name_both_parts(self):
        from types import SimpleNamespace

        from internal.models.contact import Contact

        ns = SimpleNamespace(first_name="John", last_name="Doe")
        prop = Contact.full_name
        assert prop.fget(ns) == "John Doe"

    def test_full_name_first_only(self):
        from types import SimpleNamespace

        from internal.models.contact import Contact

        ns = SimpleNamespace(first_name="John", last_name=None)
        prop = Contact.full_name
        assert prop.fget(ns) == "John"

    def test_full_name_last_only(self):
        from types import SimpleNamespace

        from internal.models.contact import Contact

        ns = SimpleNamespace(first_name=None, last_name="Doe")
        prop = Contact.full_name
        assert prop.fget(ns) == "Doe"

    def test_full_name_both_none(self):
        from types import SimpleNamespace

        from internal.models.contact import Contact

        ns = SimpleNamespace(first_name=None, last_name=None)
        prop = Contact.full_name
        assert prop.fget(ns) == ""

    def test_full_name_empty_strings(self):
        from types import SimpleNamespace

        from internal.models.contact import Contact

        ns = SimpleNamespace(first_name="", last_name="")
        prop = Contact.full_name
        assert prop.fget(ns) == ""

    def test_groups_with_memberships(self):
        from types import SimpleNamespace

        from internal.models.contact import Contact

        group_a = SimpleNamespace(name="Group A")
        group_b = SimpleNamespace(name="Group B")
        memberships = [
            SimpleNamespace(group=group_a),
            SimpleNamespace(group=group_b),
        ]
        ns = SimpleNamespace(group_memberships=memberships)
        prop = Contact.groups
        result = prop.fget(ns)
        assert result == [group_a, group_b]

    def test_groups_filters_none(self):
        from types import SimpleNamespace

        from internal.models.contact import Contact

        group_a = SimpleNamespace(name="Group A")
        memberships = [
            SimpleNamespace(group=group_a),
            SimpleNamespace(group=None),
        ]
        ns = SimpleNamespace(group_memberships=memberships)
        prop = Contact.groups
        result = prop.fget(ns)
        assert result == [group_a]

    def test_groups_empty_memberships(self):
        from types import SimpleNamespace

        from internal.models.contact import Contact

        ns = SimpleNamespace(group_memberships=[])
        prop = Contact.groups
        assert prop.fget(ns) == []

    def test_repr(self):
        from types import SimpleNamespace

        from internal.models.contact import Contact

        ns = SimpleNamespace(
            id="abc-123",
            email="test@example.com",
            status="active",
        )
        result = Contact.__repr__(ns)
        assert result == "<Contact(id=abc-123, email='test@example.com', status='active')>"


class TestContactGroupProperties:
    """Test ContactGroup computed properties without database.

    Uses SimpleNamespace + property.fget to avoid SQLAlchemy instrumentation.
    """

    def test_member_count(self):
        from types import SimpleNamespace

        from internal.models.contact import ContactGroup

        members = [SimpleNamespace(), SimpleNamespace(), SimpleNamespace()]
        ns = SimpleNamespace(members=members)
        prop = ContactGroup.member_count
        assert prop.fget(ns) == 3

    def test_member_count_empty(self):
        from types import SimpleNamespace

        from internal.models.contact import ContactGroup

        ns = SimpleNamespace(members=[])
        prop = ContactGroup.member_count
        assert prop.fget(ns) == 0

    def test_contacts_with_members(self):
        from types import SimpleNamespace

        from internal.models.contact import ContactGroup

        contact_a = SimpleNamespace(email="a@test.com")
        contact_b = SimpleNamespace(email="b@test.com")
        members = [
            SimpleNamespace(contact=contact_a),
            SimpleNamespace(contact=contact_b),
        ]
        ns = SimpleNamespace(members=members)
        prop = ContactGroup.contacts
        result = prop.fget(ns)
        assert result == [contact_a, contact_b]

    def test_contacts_filters_none(self):
        from types import SimpleNamespace

        from internal.models.contact import ContactGroup

        contact_a = SimpleNamespace(email="a@test.com")
        members = [
            SimpleNamespace(contact=contact_a),
            SimpleNamespace(contact=None),
        ]
        ns = SimpleNamespace(members=members)
        prop = ContactGroup.contacts
        result = prop.fget(ns)
        assert result == [contact_a]

    def test_contacts_empty_members(self):
        from types import SimpleNamespace

        from internal.models.contact import ContactGroup

        ns = SimpleNamespace(members=[])
        prop = ContactGroup.contacts
        assert prop.fget(ns) == []

    def test_repr(self):
        from types import SimpleNamespace

        from internal.models.contact import ContactGroup

        members = [SimpleNamespace(), SimpleNamespace()]
        ns = SimpleNamespace(id=1, slug="vip-contacts", members=members, member_count=2)
        result = ContactGroup.__repr__(ns)
        assert result == "<ContactGroup(id=1, slug='vip-contacts', members=2)>"


class TestContactGroupMemberRepr:
    """Test ContactGroupMember __repr__."""

    def test_repr(self):
        from types import SimpleNamespace

        from internal.models.contact import ContactGroupMember

        ns = SimpleNamespace(
            contact_id="abc-123",
            group_id=42,
        )
        result = ContactGroupMember.__repr__(ns)
        assert result == "<ContactGroupMember(contact_id=abc-123, group_id=42)>"


class TestContactStatusEnum:
    """Test ContactStatus enum values."""

    def test_active(self):
        from internal.models.contact import ContactStatus

        assert ContactStatus.ACTIVE == "active"
        assert ContactStatus.ACTIVE.value == "active"

    def test_unsubscribed(self):
        from internal.models.contact import ContactStatus

        assert ContactStatus.UNSUBSCRIBED == "unsubscribed"
        assert ContactStatus.UNSUBSCRIBED.value == "unsubscribed"

    def test_bounced(self):
        from internal.models.contact import ContactStatus

        assert ContactStatus.BOUNCED == "bounced"
        assert ContactStatus.BOUNCED.value == "bounced"

    def test_complained(self):
        from internal.models.contact import ContactStatus

        assert ContactStatus.COMPLAINED == "complained"
        assert ContactStatus.COMPLAINED.value == "complained"

    def test_all_values(self):
        from internal.models.contact import ContactStatus

        values = [s.value for s in ContactStatus]
        assert sorted(values) == ["active", "bounced", "complained", "unsubscribed"]
