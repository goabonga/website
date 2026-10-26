# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""User management service."""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from auth.core.security import hash_password
from auth.db.models.tenant import TenantMember, WebhookEvent
from auth.db.models.user import User, UserEmail, UserPassword, UserProfile
from auth.db.repositories.tenant import TenantRepository
from auth.db.repositories.user import UserRepository
from auth.services.tenant_role import tenant_role_service
from auth.services.webhook import safe_dispatch as dispatch_webhook_event

logger = logging.getLogger(__name__)


class UserService:
    """Service for user management operations.

    Orchestrates user-related business flows. SQL access is delegated to
    :class:`UserRepository`; this service owns transaction boundaries,
    password hashing, webhook dispatch, and multi-table creation flows.
    """

    def __init__(
        self,
        repository: UserRepository | None = None,
        *,
        tenant_repository: TenantRepository | None = None,
    ) -> None:
        self._repo = repository or UserRepository()
        self._tenant_repo = tenant_repository or TenantRepository()

    # ------------------------------------------------------------------
    # Read passthroughs
    # ------------------------------------------------------------------

    async def get_by_id(
        self,
        db: AsyncSession,
        user_id: uuid.UUID,
    ) -> User | None:
        """Get user by ID with emails and profile eager-loaded."""
        return await self._repo.find_by_id(db, user_id)

    async def get_by_email(self, db: AsyncSession, email: str) -> User | None:
        """Get user by email address."""
        return await self._repo.find_by_email(db, email)

    async def email_exists(self, db: AsyncSession, email: str) -> bool:
        """Check if email address is already registered."""
        return await self._repo.email_exists(db, email)

    async def get_user_email_row(
        self,
        db: AsyncSession,
        email: str,
    ) -> UserEmail | None:
        """Fetch a :class:`UserEmail` row by exact address (lowercased)."""
        return await self._repo.find_user_email_row(db, email)

    async def get_primary_email(
        self,
        db: AsyncSession,
        user_id: uuid.UUID,
    ) -> str | None:
        """Return the primary email address for ``user_id`` (if any)."""
        return await self._repo.find_primary_email(db, user_id)

    async def get_verified_email_with_user(
        self,
        db: AsyncSession,
        email: str,
    ) -> UserEmail | None:
        """Fetch a verified :class:`UserEmail` row with ``user`` eager-loaded."""
        return await self._repo.find_verified_email_with_user(db, email)

    async def get_by_id_with_passwords(
        self,
        db: AsyncSession,
        user_id: uuid.UUID,
    ) -> User | None:
        """Fetch a user by ID with ``passwords`` eager-loaded."""
        return await self._repo.find_by_id_with_passwords(db, user_id)

    async def get_primary_email_row(
        self,
        db: AsyncSession,
        user_id: uuid.UUID,
    ) -> UserEmail | None:
        """Fetch the primary :class:`UserEmail` row for ``user_id`` (or ``None``)."""
        return await self._repo.find_primary_email_row(db, user_id)

    async def get_first_verified_email_row(
        self,
        db: AsyncSession,
        user_id: uuid.UUID,
    ) -> UserEmail | None:
        """Fetch the oldest verified :class:`UserEmail` row for ``user_id``."""
        return await self._repo.find_first_verified_email_row(db, user_id)

    async def search_with_primary_email(
        self,
        db: AsyncSession,
        *,
        search: str,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[tuple[User, UserEmail]], int]:
        """Search users by substring on their primary email.

        See :meth:`UserRepository.search_with_primary_email`.
        """
        return await self._repo.search_with_primary_email(
            db,
            search=search,
            page=page,
            page_size=page_size,
        )

    async def list(
        self,
        db: AsyncSession,
        *,
        page: int = 1,
        page_size: int = 20,
        search: str | None = None,
        is_active: bool | None = None,
        registration_tenant_id: uuid.UUID | None = None,
        filter_no_tenant: bool = False,
    ) -> tuple[list[User], int]:
        """List users with filters and pagination. See UserRepository.list."""
        return await self._repo.list(
            db,
            page=page,
            page_size=page_size,
            search=search,
            is_active=is_active,
            registration_tenant_id=registration_tenant_id,
            filter_no_tenant=filter_no_tenant,
        )

    async def count(
        self,
        db: AsyncSession,
        *,
        is_active: bool | None = None,
        created_since: datetime | None = None,
    ) -> int:
        """Count users matching optional filters. See UserRepository.count."""
        return await self._repo.count(
            db,
            is_active=is_active,
            created_since=created_since,
        )

    # ------------------------------------------------------------------
    # Business flows
    # ------------------------------------------------------------------

    async def create_user(
        self,
        db: AsyncSession,
        email: str,
        password: str,
        profile_data: dict | None = None,
        registration_source: str | None = None,
        registration_client_id: str | None = None,
        registration_tenant_id: str | None = None,
        registration_ip: str | None = None,
        registration_user_agent: str | None = None,
    ) -> User:
        """Create a new user account with optional OIDC profile data.

        Orchestrates the multi-table creation (User, UserEmail, UserPassword,
        optional UserProfile, optional TenantMember) and dispatches the
        tenant-member webhook when auto-enrolling into a tenant.

        Args:
            db: Database session.
            email: User's email address.
            password: Plain text password (will be hashed).
            profile_data: Dictionary of OIDC profile fields. Expected keys:
                - nickname, given_name, family_name, middle_name
                - preferred_username, profile_url, picture_url, website
                - gender, birthdate, zoneinfo, locale
                - address_street, address_locality, address_region,
                  address_postal_code, address_country
                - phone_number
            registration_source: How user registered ('direct', 'api', 'oauth').
            registration_client_id: OAuth client_id that created the user.
            registration_tenant_id: Tenant ID during registration.
            registration_ip: IP address at registration.
            registration_user_agent: User agent at registration.

        Returns:
            Created User instance.

        Raises:
            ValueError: If email already exists.
        """
        # Check if email already exists
        if await self._repo.email_exists(db, email):
            logger.warning("User creation failed: email already registered: %s", email.lower())
            raise ValueError("Email already registered")

        # Create user with registration source tracking
        user = User(
            is_active=True,
            registration_source=registration_source,
            registration_client_id=registration_client_id,
            registration_tenant_id=registration_tenant_id,
            registration_ip=registration_ip,
            registration_user_agent=registration_user_agent,
        )
        await self._repo.add(db, user)

        # Create email record
        user_email = UserEmail(
            user_id=user.id,
            email=email.lower(),
            is_primary=True,
            is_verified=False,
        )
        await self._repo.add_email(db, user_email)

        # Create password record
        user_password = UserPassword(
            user_id=user.id,
            password_hash=hash_password(password),
            is_current=True,
        )
        await self._repo.add_password(db, user_password)

        # Create profile record with OIDC fields
        if profile_data:
            # Build full name from given_name, middle_name, and family_name
            name_parts = []
            if profile_data.get("given_name"):
                name_parts.append(profile_data["given_name"])
            if profile_data.get("middle_name"):
                name_parts.append(profile_data["middle_name"])
            if profile_data.get("family_name"):
                name_parts.append(profile_data["family_name"])
            full_name = " ".join(name_parts) if name_parts else None

            # Build formatted address
            address_parts = []
            if profile_data.get("address_street"):
                address_parts.append(profile_data["address_street"])
            if profile_data.get("address_locality"):
                address_parts.append(profile_data["address_locality"])
            if profile_data.get("address_region"):
                address_parts.append(profile_data["address_region"])
            if profile_data.get("address_postal_code"):
                address_parts.append(profile_data["address_postal_code"])
            if profile_data.get("address_country"):
                address_parts.append(profile_data["address_country"])
            address_formatted = ", ".join(address_parts) if address_parts else None

            user_profile = UserProfile(
                user_id=user.id,
                name=full_name,
                given_name=profile_data.get("given_name"),
                family_name=profile_data.get("family_name"),
                middle_name=profile_data.get("middle_name"),
                nickname=profile_data.get("nickname"),
                preferred_username=profile_data.get("preferred_username"),
                profile_url=profile_data.get("profile_url"),
                picture_url=profile_data.get("picture_url"),
                website=profile_data.get("website"),
                gender=profile_data.get("gender"),
                birthdate=profile_data.get("birthdate"),
                zoneinfo=profile_data.get("zoneinfo"),
                locale=profile_data.get("locale"),
                address_formatted=address_formatted,
                address_street=profile_data.get("address_street"),
                address_locality=profile_data.get("address_locality"),
                address_region=profile_data.get("address_region"),
                address_postal_code=profile_data.get("address_postal_code"),
                address_country=profile_data.get("address_country"),
                phone_number=profile_data.get("phone_number"),
            )
            await self._repo.add_profile(db, user_profile)

        # Auto-add user as member of registration tenant using the tenant's
        # configured default role (falls back to "member" by name).
        if registration_tenant_id:
            registration_tenant_uuid = (
                registration_tenant_id
                if isinstance(registration_tenant_id, uuid.UUID)
                else uuid.UUID(str(registration_tenant_id))
            )
            default_role = await tenant_role_service.resolve_default_registration_role(
                db, registration_tenant_uuid
            )
            if default_role:
                tenant_member = TenantMember(
                    tenant_id=registration_tenant_uuid,
                    user_id=user.id,
                    role_id=default_role.id,
                )
                await self._tenant_repo.add_member(db, tenant_member)
                logger.info(
                    "User auto-added as member of tenant: user_id=%s tenant_id=%s role=%s",
                    user.id,
                    registration_tenant_id,
                    default_role.name,
                )
                await dispatch_webhook_event(
                    db,
                    tenant_id=registration_tenant_uuid,
                    event=WebhookEvent.MEMBER_ADDED,
                    data={
                        "tenant_id": str(registration_tenant_uuid),
                        "user_id": str(user.id),
                        "email": email.lower(),
                        "role_id": str(default_role.id),
                        "role_name": default_role.name,
                        "source": "self_register",
                    },
                )
            else:
                logger.warning(
                    "No default role found for tenant %s, user not added as member",
                    registration_tenant_id,
                )

        await db.commit()
        await db.refresh(user)

        logger.info(
            "User created: id=%s email=%s source=%s client_id=%s tenant_id=%s",
            user.id,
            email.lower(),
            registration_source,
            registration_client_id,
            registration_tenant_id,
        )
        return user

    async def create_admin_user(
        self,
        db: AsyncSession,
        *,
        email: str,
        password: str,
        name: str | None = None,
        is_verified: bool = False,
    ) -> User:
        """Create a user from an admin action.

        Unlike :meth:`create_user` this is a narrow flow used by the admin
        panel: the admin provides only an email, password, an optional
        display name, and whether the email should be pre-verified.
        Flushes but does not commit — the caller owns the transaction
        boundary.

        Raises:
            ValueError: If the email is already registered.
        """
        if await self._repo.email_exists(db, email):
            raise ValueError("Email already registered")

        email_lower = email.lower()

        user = User(is_active=True)
        await self._repo.add(db, user)

        await self._repo.add_email(
            db,
            UserEmail(
                user_id=user.id,
                email=email_lower,
                is_primary=True,
                is_verified=is_verified,
                verified_at=datetime.now(UTC) if is_verified else None,
            ),
        )
        await self._repo.add_password(
            db,
            UserPassword(
                user_id=user.id,
                password_hash=hash_password(password),
                is_current=True,
            ),
        )
        if name:
            await self._repo.add_profile(db, UserProfile(user_id=user.id, name=name))

        await db.flush()
        return user

    async def set_active(
        self,
        db: AsyncSession,
        user: User,
        *,
        active: bool,
    ) -> None:
        """Toggle ``user.is_active`` and flush."""
        user.is_active = active
        await db.flush()

    async def delete(self, db: AsyncSession, user: User) -> None:
        """Stage a user deletion (caller owns the commit)."""
        await self._repo.delete(db, user)

    async def add_email(self, db: AsyncSession, email: UserEmail) -> UserEmail:
        """Stage a new :class:`UserEmail` row (caller owns the commit)."""
        return await self._repo.add_email(db, email)

    async def delete_email(self, db: AsyncSession, email: UserEmail) -> None:
        """Stage a :class:`UserEmail` deletion (caller owns the commit)."""
        await self._repo.delete_email(db, email)
