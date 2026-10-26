# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""CleanupRepository — sync bulk-delete queries for Celery cleanup tasks.

Celery tasks run on the sync SQLAlchemy session (``get_sync_db()``) rather
than the async session used by the rest of the app. Putting these delete
statements in a dedicated repository keeps the "no SQL outside repositories"
invariant while being explicit that this is the sync surface used only by
background workers.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, cast

from sqlalchemy import CursorResult, delete, func, or_, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from auth.db.models.oauth2 import (
    AccessToken,
    AuthorizationCode,
    DeviceCode,
    OAuth2Client,
    PARRequest,
    RefreshToken,
)
from auth.db.models.pairwise import PairwiseSubject
from auth.db.models.pat import PersonalAccessToken
from auth.db.models.tenant import Tenant, TenantWebhook, WebhookDelivery, WebhookDeliveryStatus
from auth.db.models.user import (
    MFAEmailCode,
    PasswordResetToken,
    User,
    UserEmail,
    UserProfile,
    VerificationCode,
)
from auth.db.models.user import Session as UserSession


class CleanupRepository:
    """Sync bulk deletes used by ``auth.tasks.cleanup`` Celery jobs."""

    # ------------------------------------------------------------------
    # Time-based expiry deletes (simple ``expires_at < now`` predicate)
    # ------------------------------------------------------------------

    def delete_expired_device_codes(self, db: Session, now: datetime) -> int:
        result = cast(
            CursorResult[Any],
            db.execute(delete(DeviceCode).where(DeviceCode.expires_at < now)),
        )
        return result.rowcount or 0

    def delete_expired_par_requests(self, db: Session, now: datetime) -> int:
        result = cast(
            CursorResult[Any],
            db.execute(delete(PARRequest).where(PARRequest.expires_at < now)),
        )
        return result.rowcount or 0

    def delete_expired_verification_codes(self, db: Session, now: datetime) -> int:
        result = cast(
            CursorResult[Any],
            db.execute(delete(VerificationCode).where(VerificationCode.expires_at < now)),
        )
        return result.rowcount or 0

    def delete_expired_password_reset_tokens(self, db: Session, now: datetime) -> int:
        result = cast(
            CursorResult[Any],
            db.execute(delete(PasswordResetToken).where(PasswordResetToken.expires_at < now)),
        )
        return result.rowcount or 0

    def delete_expired_mfa_email_codes(self, db: Session, now: datetime) -> int:
        result = cast(
            CursorResult[Any],
            db.execute(delete(MFAEmailCode).where(MFAEmailCode.expires_at < now)),
        )
        return result.rowcount or 0

    # ------------------------------------------------------------------
    # Compound predicates
    # ------------------------------------------------------------------

    def delete_expired_refresh_tokens(self, db: Session, now: datetime) -> int:
        result = cast(
            CursorResult[Any],
            db.execute(
                delete(RefreshToken).where(
                    or_(
                        RefreshToken.expires_at < now,
                        RefreshToken.revoked_at.isnot(None),
                    )
                )
            ),
        )
        return result.rowcount or 0

    def delete_expired_access_tokens(self, db: Session, now: datetime) -> int:
        result = cast(
            CursorResult[Any],
            db.execute(
                delete(AccessToken).where(
                    or_(
                        AccessToken.expires_at < now,
                        AccessToken.revoked_at.isnot(None),
                    )
                )
            ),
        )
        return result.rowcount or 0

    def delete_expired_authorization_codes(self, db: Session, now: datetime) -> int:
        result = cast(
            CursorResult[Any],
            db.execute(
                delete(AuthorizationCode).where(
                    or_(
                        AuthorizationCode.expires_at < now,
                        AuthorizationCode.used_at.isnot(None),
                    )
                )
            ),
        )
        return result.rowcount or 0

    def delete_expired_sessions(self, db: Session, now: datetime) -> int:
        result = cast(
            CursorResult[Any],
            db.execute(
                delete(UserSession).where(
                    or_(
                        UserSession.expires_at < now,
                        UserSession.revoked_at.isnot(None),
                    )
                )
            ),
        )
        return result.rowcount or 0

    def delete_expired_pats(
        self, db: Session, *, expired_cutoff: datetime, revoked_cutoff: datetime
    ) -> int:
        result = cast(
            CursorResult[Any],
            db.execute(
                delete(PersonalAccessToken).where(
                    or_(
                        PersonalAccessToken.expires_at < expired_cutoff,
                        PersonalAccessToken.revoked_at < revoked_cutoff,
                    )
                )
            ),
        )
        return result.rowcount or 0

    # ------------------------------------------------------------------
    # Avatar / unverified user flows (read + staged delete)
    # ------------------------------------------------------------------

    def list_referenced_picture_urls(self, db: Session) -> list[str]:
        """Return every non-null ``user_profile.picture_url``."""
        result = db.execute(
            select(UserProfile.picture_url).where(UserProfile.picture_url.isnot(None))
        )
        return [row[0] for row in result if row[0]]

    def list_unverified_users(
        self, db: Session, *, cutoff: datetime
    ) -> list[tuple[User, UserEmail, UserProfile | None]]:
        """Return ``(user, primary_email, profile)`` tuples for users whose primary
        email has not been verified and that were created before ``cutoff``.
        """
        result = db.execute(
            select(User, UserEmail, UserProfile)
            .join(UserEmail, User.id == UserEmail.user_id)
            .outerjoin(UserProfile, User.id == UserProfile.user_id)
            .where(UserEmail.is_primary.is_(True))
            .where(UserEmail.is_verified.is_(False))
            .where(User.created_at < cutoff)
        )
        return [(user, email, profile) for user, email, profile in result]

    def delete_user(self, db: Session, user: User) -> None:
        """Stage a user deletion (no commit). Cascades handle related rows."""
        db.delete(user)

    # ------------------------------------------------------------------
    # Webhook delivery housekeeping
    # ------------------------------------------------------------------

    def get_delivery_sync(
        self, db: Session, delivery_id: uuid.UUID | str
    ) -> WebhookDelivery | None:
        """Fetch a :class:`WebhookDelivery` by primary key on a sync session.

        Used by the ``deliver_webhook`` Celery task to load the delivery row
        for the current attempt. Returns ``None`` if the row no longer exists.
        """
        return db.get(WebhookDelivery, delivery_id)

    def get_webhook_sync(self, db: Session, webhook_id: uuid.UUID | str) -> TenantWebhook | None:
        """Fetch a :class:`TenantWebhook` by primary key on a sync session.

        Used by the ``deliver_webhook`` Celery task to resolve the webhook
        configuration for an in-flight delivery. Returns ``None`` if the
        webhook was deleted between enqueue and execution.
        """
        return db.get(TenantWebhook, webhook_id)

    def reset_retrying_webhook_deliveries(self, db: Session, now: datetime) -> list[uuid.UUID]:
        """Flip every retrying delivery whose ``next_retry_at`` has elapsed
        back to ``PENDING`` in a single UPDATE. Returns the affected IDs
        (so the caller can re-enqueue them)."""
        stmt = (
            update(WebhookDelivery)
            .where(
                WebhookDelivery.status == WebhookDeliveryStatus.RETRYING,
                WebhookDelivery.next_retry_at.isnot(None),
                WebhookDelivery.next_retry_at <= now,
            )
            .values(status=WebhookDeliveryStatus.PENDING, next_retry_at=None)
            .returning(WebhookDelivery.id)
        )
        result = db.execute(stmt)
        return [row[0] for row in result.all()]

    def delete_webhook_deliveries_older_than(self, db: Session, cutoff: datetime) -> int:
        """Delete delivery rows whose ``created_at`` is before ``cutoff``."""
        result = cast(
            CursorResult[Any],
            db.execute(delete(WebhookDelivery).where(WebhookDelivery.created_at < cutoff)),
        )
        return result.rowcount or 0

    def list_tenant_webhook_ids(self, db: Session) -> list[uuid.UUID]:
        """Return every tenant webhook id (used to enforce per-hook caps)."""
        return list(db.execute(select(TenantWebhook.id)).scalars().all())

    def delete_webhook_deliveries_over_cap(
        self, db: Session, webhook_id: uuid.UUID, cap: int
    ) -> int:
        """Delete the delivery rows beyond ``cap`` (newest first) for one webhook.

        Returns the number of rows deleted.
        """
        overflow_ids = (
            db.execute(
                select(WebhookDelivery.id)
                .where(WebhookDelivery.webhook_id == webhook_id)
                .order_by(WebhookDelivery.created_at.desc())
                .offset(cap)
            )
            .scalars()
            .all()
        )
        if not overflow_ids:
            return 0
        result = cast(
            CursorResult[Any],
            db.execute(delete(WebhookDelivery).where(WebhookDelivery.id.in_(overflow_ids))),
        )
        return result.rowcount or 0

    # ------------------------------------------------------------------
    # Pairwise subject backfill
    # ------------------------------------------------------------------

    def find_platform_tenant_id(self, db: Session) -> uuid.UUID | None:
        """Return the id of the platform tenant row (``is_platform=True``)."""
        result = db.execute(select(Tenant.id).where(Tenant.is_platform.is_(True)).limit(1))
        return result.scalar_one_or_none()

    def list_access_token_user_tenant_pairs(
        self, db: Session, *, fallback_tenant_id: uuid.UUID
    ) -> list[tuple[uuid.UUID, uuid.UUID]]:
        """Return distinct ``(user_id, tenant_id)`` pairs observed in
        ``access_tokens`` via the token's client. Clients without an explicit
        tenant are coalesced onto ``fallback_tenant_id``.
        Only tokens associated with a user are considered (client-credentials
        tokens are excluded).
        """
        pairs_query = (
            select(
                AccessToken.user_id,
                func.coalesce(OAuth2Client.tenant_id, fallback_tenant_id).label("tenant_id"),
            )
            .join(OAuth2Client, AccessToken.client_id == OAuth2Client.id)
            .where(AccessToken.user_id.isnot(None))
            .distinct()
        )
        rows = db.execute(pairs_query).all()
        # ``user_id`` is filtered to be non-null by the WHERE clause above.
        return cast(list[tuple[uuid.UUID, uuid.UUID]], [tuple(r) for r in rows])

    def insert_pairwise_subject_if_missing(
        self,
        db: Session,
        *,
        user_id: uuid.UUID,
        tenant_id: uuid.UUID,
    ) -> bool:
        """Insert a ``PairwiseSubject`` row. Returns True if the row was
        actually created, False if the ``uq_pairwise_user_tenant`` constraint
        already held.
        """
        stmt = (
            pg_insert(PairwiseSubject)
            .values(
                id=uuid.uuid4(),
                user_id=user_id,
                tenant_id=tenant_id,
                sub_value=uuid.uuid4(),
            )
            .on_conflict_do_nothing(constraint="uq_pairwise_user_tenant")
        )
        result = cast(CursorResult[Any], db.execute(stmt))
        return (result.rowcount or 0) > 0


cleanup_repository = CleanupRepository()
