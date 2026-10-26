# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for auth.db.models.tenant — Tenant model methods and properties."""

import uuid
from unittest.mock import MagicMock

from auth.db.models.tenant import (
    DEFAULT_TENANT_ROLES,
    TENANT_SCOPES,
    CustomDomainStatus,
    FederatedIdentity,
    IdentityProvider,
    IdentityProviderType,
    Tenant,
    TenantBranding,
    TenantCustomRole,
    TenantMember,
    TenantRole,
    TenantTemplate,
    TenantTrustedSource,
    TenantTrustMode,
    TenantWebhook,
    WebhookDelivery,
    WebhookDeliveryStatus,
    WebhookEvent,
)

# ── Enums ─────────────────────────────────────────────────────────────────────


class TestEnums:
    def test_tenant_role_values(self):
        assert TenantRole.OWNER == "owner"
        assert TenantRole.ADMIN == "admin"
        assert TenantRole.MEMBER == "member"

    def test_custom_domain_status_values(self):
        assert CustomDomainStatus.PENDING == "pending"
        assert CustomDomainStatus.ACTIVE == "active"
        assert CustomDomainStatus.FAILED == "failed"

    def test_identity_provider_type_values(self):
        assert IdentityProviderType.OIDC == "oidc"
        assert IdentityProviderType.GOOGLE == "google"
        assert IdentityProviderType.GITHUB == "github"
        assert IdentityProviderType.MICROSOFT == "microsoft"
        assert IdentityProviderType.SAML == "saml"

    def test_trust_mode_values(self):
        assert TenantTrustMode.NONE == "none"
        assert TenantTrustMode.ALL == "all"
        assert TenantTrustMode.MEMBERS_ONLY == "members_only"
        assert TenantTrustMode.SPECIFIC == "specific"


# ── TenantCustomRole.has_scope ────────────────────────────────────────────────


def _make_custom_role(scopes):
    """Create a mock TenantCustomRole with real has_scope method."""
    role = MagicMock(spec=TenantCustomRole)
    role.scopes = scopes
    role.has_scope = lambda req: TenantCustomRole.has_scope(role, req)
    return role


class TestTenantCustomRoleHasScope:
    def test_global_wildcard(self):
        role = _make_custom_role(["*"])
        assert role.has_scope("members:read") is True

    def test_exact_match(self):
        role = _make_custom_role(["members:read"])
        assert role.has_scope("members:read") is True

    def test_resource_wildcard(self):
        role = _make_custom_role(["members:*"])
        assert role.has_scope("members:read") is True
        assert role.has_scope("members:invite") is True

    def test_no_match(self):
        role = _make_custom_role(["settings:read"])
        assert role.has_scope("members:read") is False

    def test_empty_scopes(self):
        role = _make_custom_role([])
        assert role.has_scope("members:read") is False

    def test_none_scopes(self):
        role = _make_custom_role(None)
        assert role.has_scope("members:read") is False

    def test_scope_without_colon(self):
        role = _make_custom_role(["admin"])
        assert role.has_scope("admin") is True

    def test_multiple_scopes(self):
        role = _make_custom_role(["members:read", "settings:write"])
        assert role.has_scope("members:read") is True
        assert role.has_scope("settings:write") is True
        assert role.has_scope("roles:read") is False


# ── TenantMember properties ──────────────────────────────────────────────────


def _make_member(custom_role=None):
    """Create a mock TenantMember with real properties."""
    member = MagicMock(spec=TenantMember)
    member.custom_role = custom_role
    type(member).role_name = TenantMember.role_name
    type(member).role_display_name = TenantMember.role_display_name
    member.has_scope = lambda req: TenantMember.has_scope(member, req)
    return member


class TestTenantMemberRoleName:
    def test_with_custom_role(self):
        role = MagicMock()
        role.name = "editor"
        member = _make_member(custom_role=role)
        assert member.role_name == "editor"

    def test_without_custom_role(self):
        member = _make_member(custom_role=None)
        assert member.role_name == "member"


class TestTenantMemberRoleDisplayName:
    def test_with_custom_role(self):
        role = MagicMock()
        role.display_name = "Content Editor"
        member = _make_member(custom_role=role)
        assert member.role_display_name == "Content Editor"

    def test_without_custom_role(self):
        member = _make_member(custom_role=None)
        assert member.role_display_name == "Member"


class TestTenantMemberHasScope:
    def test_with_custom_role(self):
        role = _make_custom_role(["members:read", "settings:write"])
        member = _make_member(custom_role=role)
        assert member.has_scope("members:read") is True
        assert member.has_scope("settings:write") is True
        assert member.has_scope("roles:write") is False

    def test_without_custom_role_basic_read(self):
        member = _make_member(custom_role=None)
        assert member.has_scope("members:read") is True

    def test_without_custom_role_no_write(self):
        member = _make_member(custom_role=None)
        assert member.has_scope("members:write") is False


# ── __repr__ methods ──────────────────────────────────────────────────────────


class TestReprs:
    def test_tenant_repr(self):
        t = MagicMock(spec=Tenant)
        t.slug = "acme"
        t.is_active = True
        t.__repr__ = Tenant.__repr__
        assert "acme" in repr(t)

    def test_tenant_custom_role_repr(self):
        r = MagicMock(spec=TenantCustomRole)
        r.tenant_id = uuid.uuid4()
        r.name = "editor"
        r.__repr__ = TenantCustomRole.__repr__
        result = repr(r)
        assert "editor" in result

    def test_tenant_member_repr(self):
        m = MagicMock(spec=TenantMember)
        m.tenant_id = uuid.uuid4()
        m.user_id = uuid.uuid4()
        m.custom_role = None
        type(m).role_name = TenantMember.role_name
        m.__repr__ = TenantMember.__repr__
        result = repr(m)
        assert "TenantMember" in result

    def test_identity_provider_repr(self):
        idp = MagicMock(spec=IdentityProvider)
        idp.name = "Google"
        idp.provider_type = IdentityProviderType.GOOGLE
        idp.tenant_id = uuid.uuid4()
        idp.__repr__ = IdentityProvider.__repr__
        result = repr(idp)
        assert "Google" in result

    def test_tenant_branding_repr(self):
        b = MagicMock(spec=TenantBranding)
        b.tenant_id = uuid.uuid4()
        b.__repr__ = TenantBranding.__repr__
        result = repr(b)
        assert "TenantBranding" in result

    def test_tenant_template_repr(self):
        t = MagicMock(spec=TenantTemplate)
        t.tenant_id = uuid.uuid4()
        t.template_name = "auth/login.html"
        t.__repr__ = TenantTemplate.__repr__
        result = repr(t)
        assert "auth/login.html" in result

    def test_federated_identity_repr(self):
        fi = MagicMock(spec=FederatedIdentity)
        fi.user_id = uuid.uuid4()
        fi.identity_provider_id = uuid.uuid4()
        fi.external_subject = "ext_123"
        fi.__repr__ = FederatedIdentity.__repr__
        result = repr(fi)
        assert "ext_123" in result

    def test_tenant_trusted_source_repr(self):
        ts = MagicMock(spec=TenantTrustedSource)
        ts.tenant_id = uuid.uuid4()
        ts.trusted_tenant_id = uuid.uuid4()
        ts.__repr__ = TenantTrustedSource.__repr__
        result = repr(ts)
        assert "TenantTrustedSource" in result


# ── Constants ────────────────────────────────────────────────────────────────


class TestConstants:
    def test_tenant_scopes_has_wildcard(self):
        assert "*" in TENANT_SCOPES

    def test_default_tenant_roles_has_owner(self):
        assert "owner" in DEFAULT_TENANT_ROLES
        assert DEFAULT_TENANT_ROLES["owner"]["scopes"] == ["*"]

    def test_default_tenant_roles_has_member(self):
        assert "member" in DEFAULT_TENANT_ROLES

    def test_tenant_scopes_has_webhooks(self):
        assert "webhooks:*" in TENANT_SCOPES
        assert "webhooks:read" in TENANT_SCOPES
        assert "webhooks:write" in TENANT_SCOPES
        assert "webhooks:delete" in TENANT_SCOPES

    def test_admin_role_inherits_webhooks(self):
        assert "webhooks:*" in DEFAULT_TENANT_ROLES["admin"]["scopes"]

    def test_tenant_scopes_has_custom_domain(self):
        assert "domain:*" in TENANT_SCOPES
        assert "domain:read" in TENANT_SCOPES
        assert "domain:write" in TENANT_SCOPES

    def test_custom_domain_writes_are_reserved_to_owners_by_default(self):
        """Only the owner (`*`) may change the domain; the admin role may follow its status."""
        for name, config in DEFAULT_TENANT_ROLES.items():
            granted = [s for s in config["scopes"] if s == "*" or s.startswith("domain:")]
            expected = {"owner": ["*"], "admin": ["domain:read"]}.get(name, [])
            assert granted == expected

    def test_settings_write_does_not_grant_custom_domain(self):
        role = _make_custom_role(["settings:*"])
        assert role.has_scope("settings:write") is True
        assert role.has_scope("domain:write") is False

    def test_domain_wildcard_grants_both_custom_domain_scopes(self):
        role = _make_custom_role(["domain:*"])
        assert role.has_scope("domain:read") is True
        assert role.has_scope("domain:write") is True
        assert role.has_scope("settings:write") is False


# ── Webhooks ─────────────────────────────────────────────────────────────────


class TestWebhookEnums:
    def test_webhook_delivery_status_values(self):
        assert WebhookDeliveryStatus.PENDING == "pending"
        assert WebhookDeliveryStatus.SUCCESS == "success"
        assert WebhookDeliveryStatus.FAILED == "failed"
        assert WebhookDeliveryStatus.RETRYING == "retrying"

    def test_webhook_event_has_user_lifecycle(self):
        assert WebhookEvent.USER_CREATED == "user.created"
        assert WebhookEvent.USER_DELETED == "user.deleted"

    def test_webhook_event_has_auth(self):
        assert WebhookEvent.LOGIN_SUCCESS == "login.success"
        assert WebhookEvent.LOGIN_FAILED == "login.failed"

    def test_webhook_event_has_mfa(self):
        assert WebhookEvent.MFA_ENABLED == "mfa.enabled"
        assert WebhookEvent.MFA_CHALLENGE_FAILED == "mfa.challenge.failed"

    def test_webhook_event_has_oauth2(self):
        assert WebhookEvent.OAUTH2_TOKEN_ISSUED == "oauth2.token.issued"
        assert WebhookEvent.OAUTH2_CONSENT_GRANTED == "oauth2.consent.granted"

    def test_webhook_event_has_tenant(self):
        assert WebhookEvent.TENANT_DOMAIN_VERIFIED == "tenant.domain.verified"

    def test_webhook_event_has_webhook_test(self):
        assert WebhookEvent.WEBHOOK_TEST == "webhook.test"

    def test_webhook_event_values_are_dot_notation(self):
        for ev in WebhookEvent:
            # The logout event is a single token; everything else is {group}.{action}...
            if ev is not WebhookEvent.LOGOUT:
                assert "." in ev.value, f"Event {ev.name} is not dot-notation"


class TestWebhookReprs:
    def test_tenant_webhook_repr(self):
        w = MagicMock(spec=TenantWebhook)
        w.id = uuid.uuid4()
        w.tenant_id = uuid.uuid4()
        w.url = "https://example.com/hook"
        w.__repr__ = TenantWebhook.__repr__
        result = repr(w)
        assert "TenantWebhook" in result
        assert "example.com" in result

    def test_webhook_delivery_repr(self):
        d = MagicMock(spec=WebhookDelivery)
        d.id = uuid.uuid4()
        d.event = "user.created"
        d.status = WebhookDeliveryStatus.RETRYING
        d.attempt = 2
        d.max_attempts = 5
        d.__repr__ = WebhookDelivery.__repr__
        result = repr(d)
        assert "user.created" in result
        assert "2/5" in result


class TestBuildScopeGroupsFromDb:
    """The built-in catalogue is merged in, but never shadows a DB scope."""

    def _db_scope(self, name, description="From DB", resource="users", category="identity"):
        scope = MagicMock()
        scope.name = name
        scope.description = description
        scope.resource = resource
        scope.category = category
        return scope

    def test_builtin_scopes_are_added_when_absent(self):
        from auth.db.models.tenant import BUILTIN_SCOPES, build_scope_groups_from_db

        groups = build_scope_groups_from_db([])

        flattened = {
            name
            for resources in groups.values()
            for pairs in resources.values()
            for name, _desc in pairs
        }
        assert flattened == {name for name, _d, _c, _r in BUILTIN_SCOPES}

    def test_a_db_scope_shadows_its_builtin_namesake(self):
        from auth.db.models.tenant import BUILTIN_SCOPES, build_scope_groups_from_db

        builtin_name, _d, builtin_cat, builtin_res = BUILTIN_SCOPES[0]
        groups = build_scope_groups_from_db([self._db_scope(builtin_name, description="From DB")])

        entries = [
            (name, desc)
            for resources in groups.values()
            for pairs in resources.values()
            for name, desc in pairs
            if name == builtin_name
        ]
        assert entries == [(builtin_name, "From DB")]
        # The built-in copy was not re-added under its own category/resource.
        assert builtin_name not in [
            name for name, _desc in groups.get(builtin_cat, {}).get(builtin_res, [])
        ]

    def test_missing_category_and_resource_fall_back_to_other(self):
        from auth.db.models.tenant import build_scope_groups_from_db

        scope = self._db_scope("custom:read", description=None, resource=None, category=None)

        groups = build_scope_groups_from_db([scope])

        assert groups["Other"]["Other"] == [("custom:read", "custom:read")]
