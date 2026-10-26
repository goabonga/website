# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Database cleanup tasks for expired records."""

import logging
from datetime import UTC, datetime, timedelta

from auth.celery import celery_app
from auth.config import settings
from auth.core.database import get_sync_db
from auth.db.repositories.cleanup import cleanup_repository
from auth.services.upload import upload_service

logger = logging.getLogger(__name__)


@celery_app.task(name="cleanup_expired_tokens")
def cleanup_expired_tokens() -> dict:
    """Delete expired or revoked access tokens and refresh tokens.

    Returns:
        Dict with counts of deleted records.
    """
    now = datetime.now(UTC)

    with get_sync_db() as db:
        # Delete expired or revoked refresh tokens first (due to FK constraint)
        refresh_deleted = cleanup_repository.delete_expired_refresh_tokens(db, now)
        access_deleted = cleanup_repository.delete_expired_access_tokens(db, now)

    logger.info(
        "Cleanup completed: %d access tokens, %d refresh tokens deleted",
        access_deleted,
        refresh_deleted,
    )

    return {
        "access_tokens_deleted": access_deleted,
        "refresh_tokens_deleted": refresh_deleted,
    }


@celery_app.task(name="cleanup_expired_authorization_codes")
def cleanup_expired_authorization_codes() -> dict:
    """Delete expired or used authorization codes.

    Returns:
        Dict with count of deleted records.
    """
    now = datetime.now(UTC)

    with get_sync_db() as db:
        deleted = cleanup_repository.delete_expired_authorization_codes(db, now)

    logger.info("Cleanup completed: %d authorization codes deleted", deleted)

    return {"authorization_codes_deleted": deleted}


@celery_app.task(name="cleanup_expired_device_codes")
def cleanup_expired_device_codes() -> dict:
    """Delete expired device codes.

    Returns:
        Dict with count of deleted records.
    """
    now = datetime.now(UTC)

    with get_sync_db() as db:
        deleted = cleanup_repository.delete_expired_device_codes(db, now)

    logger.info("Cleanup completed: %d device codes deleted", deleted)

    return {"device_codes_deleted": deleted}


@celery_app.task(name="cleanup_expired_par_requests")
def cleanup_expired_par_requests() -> dict:
    """Delete expired Pushed Authorization Requests (RFC 9126).

    Returns:
        Dict with count of deleted records.
    """
    now = datetime.now(UTC)

    with get_sync_db() as db:
        deleted = cleanup_repository.delete_expired_par_requests(db, now)

    logger.info("Cleanup completed: %d PAR requests deleted", deleted)

    return {"par_requests_deleted": deleted}


@celery_app.task(name="cleanup_expired_verification_codes")
def cleanup_expired_verification_codes() -> dict:
    """Delete expired email verification codes.

    Returns:
        Dict with count of deleted records.
    """
    now = datetime.now(UTC)

    with get_sync_db() as db:
        deleted = cleanup_repository.delete_expired_verification_codes(db, now)

    logger.info("Cleanup completed: %d verification codes deleted", deleted)

    return {"verification_codes_deleted": deleted}


@celery_app.task(name="cleanup_expired_password_reset_tokens")
def cleanup_expired_password_reset_tokens() -> dict:
    """Delete expired password reset tokens.

    Returns:
        Dict with count of deleted records.
    """
    now = datetime.now(UTC)

    with get_sync_db() as db:
        deleted = cleanup_repository.delete_expired_password_reset_tokens(db, now)

    logger.info("Cleanup completed: %d password reset tokens deleted", deleted)

    return {"password_reset_tokens_deleted": deleted}


@celery_app.task(name="cleanup_expired_mfa_email_codes")
def cleanup_expired_mfa_email_codes() -> dict:
    """Delete expired MFA email verification codes.

    Returns:
        Dict with count of deleted records.
    """
    now = datetime.now(UTC)

    with get_sync_db() as db:
        deleted = cleanup_repository.delete_expired_mfa_email_codes(db, now)

    logger.info("Cleanup completed: %d MFA email codes deleted", deleted)

    return {"mfa_email_codes_deleted": deleted}


@celery_app.task(name="cleanup_expired_sessions")
def cleanup_expired_sessions() -> dict:
    """Delete expired or revoked user sessions.

    Returns:
        Dict with count of deleted records.
    """
    now = datetime.now(UTC)

    with get_sync_db() as db:
        deleted = cleanup_repository.delete_expired_sessions(db, now)

    logger.info("Cleanup completed: %d sessions deleted", deleted)

    return {"sessions_deleted": deleted}


@celery_app.task(name="cleanup_expired_pats")
def cleanup_expired_pats() -> dict:
    """Delete expired and revoked Personal Access Tokens.

    Tokens are deleted after a grace period:
    - Expired tokens: 30 days after expiration
    - Revoked tokens: 90 days after revocation

    Returns:
        Dict with counts of deleted records.
    """
    now = datetime.now(UTC)
    expired_cutoff = now - timedelta(days=30)
    revoked_cutoff = now - timedelta(days=90)

    with get_sync_db() as db:
        deleted = cleanup_repository.delete_expired_pats(
            db, expired_cutoff=expired_cutoff, revoked_cutoff=revoked_cutoff
        )

    logger.info("Cleanup completed: %d personal access tokens deleted", deleted)

    return {"pats_deleted": deleted}


@celery_app.task(name="cleanup_orphaned_avatars")
def cleanup_orphaned_avatars() -> dict:
    """Delete avatar files that are no longer referenced by any user profile.

    This task:
    1. Lists all avatar files on disk
    2. Gets all picture_url values from user_profiles table
    3. Deletes files that are not referenced by any user

    Returns:
        Dict with count of deleted files.
    """
    if not settings.orphan_avatar_cleanup_enabled:
        logger.info("Orphan avatar cleanup is disabled")
        return {"avatars_deleted": 0, "skipped": True}

    # Get all avatar files from disk
    avatar_files = set(upload_service.list_avatar_files())

    if not avatar_files:
        logger.info("No avatar files found on disk")
        return {"avatars_deleted": 0}

    # Get all referenced avatar filenames from database
    referenced_files: set[str] = set()
    with get_sync_db() as db:
        for picture_url in cleanup_repository.list_referenced_picture_urls(db):
            if "/avatars/" in picture_url:
                filename = picture_url.split("/avatars/")[-1]
                referenced_files.add(filename)

    # Find orphaned files (on disk but not in database)
    orphaned_files = avatar_files - referenced_files

    # Delete orphaned files
    deleted_count = 0
    for filename in orphaned_files:
        if upload_service.delete_avatar_by_filename(filename):
            deleted_count += 1
            logger.debug("Deleted orphaned avatar: %s", filename)

    logger.info(
        "Cleanup completed: %d orphaned avatars deleted (total on disk: %d, referenced: %d)",
        deleted_count,
        len(avatar_files),
        len(referenced_files),
    )

    return {"avatars_deleted": deleted_count}


@celery_app.task(name="cleanup_unverified_users")
def cleanup_unverified_users() -> dict:
    """Delete users who haven't verified their email within the configured period.

    This task:
    1. Finds users with unverified primary email older than expiry_days
    2. Deletes their avatar files if any
    3. Deletes the users (cascade handles related records)

    Returns:
        Dict with counts of deleted users and avatars.
    """
    now = datetime.now(UTC)
    cutoff = now - timedelta(days=settings.unverified_user_expiry_days)

    users_deleted = 0
    avatars_deleted = 0

    with get_sync_db() as db:
        users_to_delete = cleanup_repository.list_unverified_users(db, cutoff=cutoff)

        for user, email, profile in users_to_delete:
            # Delete avatar file if exists
            picture_url = profile.picture_url if profile else None
            if picture_url and "/avatars/" in picture_url:
                filename = picture_url.split("/avatars/")[-1]
                if upload_service.delete_avatar_by_filename(filename):
                    avatars_deleted += 1

            # Delete user (cascade handles emails, profile, sessions, etc.)
            cleanup_repository.delete_user(db, user)
            users_deleted += 1
            logger.info("Deleted unverified user: %s (created: %s)", email.email, user.created_at)

        db.commit()

    logger.info(
        "Cleanup completed: %d unverified users deleted, %d avatars removed",
        users_deleted,
        avatars_deleted,
    )

    return {
        "users_deleted": users_deleted,
        "avatars_deleted": avatars_deleted,
    }
