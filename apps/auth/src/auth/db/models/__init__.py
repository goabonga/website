# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Database models."""

from auth.db.models.jwk import JWK
from auth.db.models.oauth2 import (
    AccessToken,
    AuthorizationCode,
    DeviceCode,
    DeviceCodeStatus,
    OAuth2Client,
    PARRequest,
    RefreshToken,
)
from auth.db.models.pairwise import PairwiseSubject
from auth.db.models.pat import (
    PATExpirationPreset,
    PersonalAccessToken,
)
from auth.db.models.rbac import (
    ADMIN_SCOPES,
    DEFAULT_ROLES,
    Role,
    RoleScope,
    Scope,
    UserRole,
)
from auth.db.models.tenant import (
    FederatedIdentity,
    IdentityProvider,
    IdentityProviderType,
    Tenant,
    TenantCustomRole,
    TenantMember,
    TenantRole,
    TenantWebhook,
    WebhookDelivery,
    WebhookDeliveryStatus,
    WebhookEvent,
)
from auth.db.models.user import (
    MFABackupCode,
    MFAEmailCode,
    PasswordResetToken,
    Session,
    User,
    UserEmail,
    UserMFA,
    UserPassword,
    UserProfile,
    VerificationCode,
)

__all__ = [
    "AccessToken",
    "ADMIN_SCOPES",
    "AuthorizationCode",
    "DEFAULT_ROLES",
    "DeviceCode",
    "DeviceCodeStatus",
    "FederatedIdentity",
    "IdentityProvider",
    "IdentityProviderType",
    "JWK",
    "MFABackupCode",
    "MFAEmailCode",
    "OAuth2Client",
    "PARRequest",
    "PATExpirationPreset",
    "PairwiseSubject",
    "PasswordResetToken",
    "PersonalAccessToken",
    "RefreshToken",
    "Role",
    "RoleScope",
    "Scope",
    "Session",
    "Tenant",
    "TenantCustomRole",
    "TenantMember",
    "TenantRole",
    "TenantWebhook",
    "User",
    "UserEmail",
    "UserMFA",
    "UserPassword",
    "UserProfile",
    "UserRole",
    "VerificationCode",
    "WebhookDelivery",
    "WebhookDeliveryStatus",
    "WebhookEvent",
]
