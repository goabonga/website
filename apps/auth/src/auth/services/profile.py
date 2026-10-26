# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Profile service for user profile management."""

import logging
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from auth.db.models.user import UserProfile
from auth.db.repositories.profile import ProfileRepository

logger = logging.getLogger(__name__)


@dataclass
class ProfileData:
    """Profile data for updates."""

    nickname: str | None = None
    given_name: str | None = None
    family_name: str | None = None
    middle_name: str | None = None
    name: str | None = None
    preferred_username: str | None = None
    picture_url: str | None = None
    profile_url: str | None = None
    website: str | None = None
    gender: str | None = None
    birthdate: str | None = None
    zoneinfo: str | None = None
    locale: str | None = None
    phone_number: str | None = None
    # Address fields
    address_street: str | None = None
    address_locality: str | None = None
    address_region: str | None = None
    address_postal_code: str | None = None
    address_country: str | None = None


class ProfileService:
    """Service for user profile operations.

    Orchestrates profile-related business flows (sparse updates, auto-name
    generation). SQL access is delegated to :class:`ProfileRepository`;
    transaction boundaries stay with the caller.
    """

    def __init__(self, repository: ProfileRepository | None = None) -> None:
        self._repo = repository or ProfileRepository()

    async def get_profile(
        self,
        db: AsyncSession,
        user_id: str,
    ) -> UserProfile | None:
        """Get user profile by user ID.

        Args:
            db: Database session.
            user_id: User ID.

        Returns:
            UserProfile if found, None otherwise.
        """
        return await self._repo.find_by_user_id(db, user_id)

    async def add_profile(self, db: AsyncSession, profile: UserProfile) -> UserProfile:
        """Stage a new :class:`UserProfile` row (no commit).

        Used by admin edit flows that discover the profile is missing
        after loading the user. The caller owns the transaction boundary.
        """
        await self._repo.stage(db, profile)
        return profile

    async def get_or_create_profile(
        self,
        db: AsyncSession,
        user_id: str,
    ) -> UserProfile:
        """Get user profile or create one if it doesn't exist.

        Args:
            db: Database session.
            user_id: User ID.

        Returns:
            UserProfile instance.
        """
        profile = await self.get_profile(db, user_id)

        if not profile:
            logger.info("Creating new profile for user_id=%s", user_id)
            profile = UserProfile(user_id=user_id)
            await self._repo.add(db, profile)

        return profile

    async def update_profile(
        self,
        db: AsyncSession,
        user_id: str,
        data: ProfileData,
    ) -> UserProfile:
        """Update user profile.

        Args:
            db: Database session.
            user_id: User ID.
            data: Profile data to update.

        Returns:
            Updated UserProfile.
        """
        profile = await self.get_or_create_profile(db, user_id)

        # Update fields if provided
        if data.nickname is not None:
            profile.nickname = data.nickname.strip() if data.nickname else None

        if data.given_name is not None:
            profile.given_name = data.given_name.strip() if data.given_name else None

        if data.family_name is not None:
            profile.family_name = data.family_name.strip() if data.family_name else None

        if data.name is not None:
            profile.name = data.name.strip() if data.name else None
        elif data.given_name is not None or data.family_name is not None:
            # Auto-generate full name from given/family name if not explicitly set
            parts = []
            if profile.given_name:
                parts.append(profile.given_name)
            if profile.family_name:
                parts.append(profile.family_name)
            profile.name = " ".join(parts) if parts else None

        if data.picture_url is not None:
            profile.picture_url = data.picture_url.strip() if data.picture_url else None

        if data.website is not None:
            profile.website = data.website.strip() if data.website else None

        if data.preferred_username is not None:
            profile.preferred_username = (
                data.preferred_username.strip() if data.preferred_username else None
            )

        if data.middle_name is not None:
            profile.middle_name = data.middle_name.strip() if data.middle_name else None

        if data.profile_url is not None:
            profile.profile_url = data.profile_url.strip() if data.profile_url else None

        if data.gender is not None:
            profile.gender = data.gender.strip() if data.gender else None

        if data.birthdate is not None:
            profile.birthdate = data.birthdate.strip() if data.birthdate else None

        if data.zoneinfo is not None:
            profile.zoneinfo = data.zoneinfo.strip() if data.zoneinfo else None

        if data.locale is not None:
            profile.locale = data.locale.strip() if data.locale else None

        if data.phone_number is not None:
            profile.phone_number = data.phone_number.strip() if data.phone_number else None

        # Address fields
        if data.address_street is not None:
            profile.address_street = data.address_street.strip() if data.address_street else None

        if data.address_locality is not None:
            profile.address_locality = (
                data.address_locality.strip() if data.address_locality else None
            )

        if data.address_region is not None:
            profile.address_region = data.address_region.strip() if data.address_region else None

        if data.address_postal_code is not None:
            profile.address_postal_code = (
                data.address_postal_code.strip() if data.address_postal_code else None
            )

        if data.address_country is not None:
            profile.address_country = data.address_country.strip() if data.address_country else None

        await self._repo.flush(db)

        logger.info("Profile updated for user_id=%s", user_id)
        return profile

    def profile_to_dict(self, profile: UserProfile | None) -> dict:
        """Convert profile to dictionary.

        Args:
            profile: UserProfile instance or None.

        Returns:
            Dictionary with profile data.
        """
        if not profile:
            return {
                "nickname": None,
                "name": None,
                "given_name": None,
                "family_name": None,
                "middle_name": None,
                "preferred_username": None,
                "picture_url": None,
                "profile_url": None,
                "website": None,
                "gender": None,
                "birthdate": None,
                "zoneinfo": None,
                "locale": None,
                "phone_number": None,
                "address_street": None,
                "address_locality": None,
                "address_region": None,
                "address_postal_code": None,
                "address_country": None,
            }

        return {
            "nickname": profile.nickname,
            "name": profile.name,
            "given_name": profile.given_name,
            "family_name": profile.family_name,
            "middle_name": profile.middle_name,
            "preferred_username": profile.preferred_username,
            "picture_url": profile.picture_url,
            "profile_url": profile.profile_url,
            "website": profile.website,
            "gender": profile.gender,
            "birthdate": profile.birthdate,
            "zoneinfo": profile.zoneinfo,
            "locale": profile.locale,
            "phone_number": profile.phone_number,
            "address_street": profile.address_street,
            "address_locality": profile.address_locality,
            "address_region": profile.address_region,
            "address_postal_code": profile.address_postal_code,
            "address_country": profile.address_country,
        }
