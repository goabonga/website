# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Prompt service for managing system prompts."""

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from backend.logging import get_logger
from backend.models.prompt import SystemPrompt, SystemPromptVersion
from backend.prompts.cache import prompt_cache

logger = get_logger(__name__)

# Fallback prompt if database is unavailable
DEFAULT_FALLBACK_PROMPT = """You are a helpful AI assistant. You provide accurate, helpful, and concise responses.

When responding:
- Be direct and helpful
- If you used information from the knowledge base, integrate it naturally
- If you don't know something, say so honestly
- Keep responses focused and relevant
"""


class PromptService:
    """Service for managing system prompts with caching and versioning."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_prompt_for_scopes(self, user_scopes: set[str] | None) -> str:
        """Get the best matching prompt for user scopes.

        Selection logic:
        1. Check cache first
        2. Query all prompts from DB
        3. Filter by accessibility (user must have required scopes)
        4. Select most specific match (highest number of required scopes)
        5. Fall back to default prompt if no match
        6. Fall back to hardcoded prompt if DB fails

        Args:
            user_scopes: User's scopes (None for anonymous users)

        Returns:
            The prompt content string
        """
        # Check scope cache first
        cached = await prompt_cache.get_for_scopes(user_scopes)
        if cached:
            return cached

        try:
            # Query all prompts with their versions
            stmt = select(SystemPrompt)
            result = await self.session.execute(stmt)
            prompts = result.scalars().all()

            if not prompts:
                logger.warning("No prompts found in database, using fallback")
                return DEFAULT_FALLBACK_PROMPT

            # Filter accessible prompts and find best match
            accessible_prompts: list[SystemPrompt] = []
            default_prompt: SystemPrompt | None = None

            for prompt in prompts:
                if prompt.is_default:
                    default_prompt = prompt
                if prompt.is_accessible(user_scopes):
                    accessible_prompts.append(prompt)

            # Sort by specificity (most required scopes first)
            accessible_prompts.sort(key=lambda p: p.get_specificity(), reverse=True)

            # Select the most specific non-default prompt, or default
            selected_prompt: SystemPrompt | None = None
            for prompt in accessible_prompts:
                if not prompt.is_default:
                    selected_prompt = prompt
                    break

            # Fall back to default if no specific match
            if not selected_prompt:
                selected_prompt = default_prompt

            if not selected_prompt:
                logger.warning("No accessible or default prompt found, using fallback")
                return DEFAULT_FALLBACK_PROMPT

            # Get current version content
            current_version = selected_prompt.get_current_version()
            if not current_version:
                logger.warning(
                    "Prompt %s has no current version, using fallback",
                    selected_prompt.slug,
                )
                return DEFAULT_FALLBACK_PROMPT

            content = current_version.content

            # Cache the result
            await prompt_cache.set_for_scopes(user_scopes, content)

            logger.debug(
                "Selected prompt '%s' (v%d) for scopes: %s",
                selected_prompt.slug,
                current_version.version,
                user_scopes,
            )

            return content

        except Exception as e:
            logger.error("Failed to get prompt for scopes: %s", e)
            return DEFAULT_FALLBACK_PROMPT

    async def get_prompt_by_slug(self, slug: str) -> SystemPrompt | None:
        """Get a prompt by its slug.

        Args:
            slug: The prompt slug

        Returns:
            SystemPrompt or None if not found
        """
        stmt = select(SystemPrompt).where(SystemPrompt.slug == slug)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_default_prompt(self) -> SystemPrompt | None:
        """Get the default prompt.

        Returns:
            The default SystemPrompt or None
        """
        stmt = select(SystemPrompt).where(SystemPrompt.is_default.is_(True))
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def create_prompt(
        self,
        slug: str,
        name: str,
        content: str,
        description: str | None = None,
        required_scopes: list[str] | None = None,
        is_default: bool = False,
        metadata: dict | None = None,
    ) -> SystemPrompt:
        """Create a new prompt with initial version.

        Args:
            slug: Unique slug identifier
            name: Display name
            content: Initial prompt content
            description: Optional description
            required_scopes: Scopes required to use this prompt
            is_default: Whether this is the default prompt
            metadata: Optional metadata for the version

        Returns:
            The created SystemPrompt
        """
        # If setting as default, unset any existing default
        if is_default:
            await self.session.execute(
                update(SystemPrompt)
                .where(SystemPrompt.is_default.is_(True))
                .values(is_default=False)
            )

        # Create prompt
        prompt = SystemPrompt(
            slug=slug,
            name=name,
            description=description,
            required_scopes=required_scopes,
            is_default=is_default,
        )
        self.session.add(prompt)
        await self.session.flush()  # Get the ID

        # Create initial version
        version = SystemPromptVersion(
            prompt_id=prompt.id,
            version=1,
            content=content,
            metadata_=metadata or {},
            is_current=True,
        )
        self.session.add(version)

        await self.session.commit()
        await self.session.refresh(prompt)

        # Invalidate cache
        await prompt_cache.invalidate()

        logger.info("Created prompt '%s' with initial version", slug)
        return prompt

    async def create_version(
        self,
        prompt_id: int,
        content: str,
        metadata: dict | None = None,
    ) -> SystemPromptVersion:
        """Create a new version of a prompt.

        Args:
            prompt_id: The prompt ID
            content: New prompt content
            metadata: Optional metadata

        Returns:
            The created SystemPromptVersion
        """
        # Get current max version
        stmt = (
            select(SystemPromptVersion.version)
            .where(SystemPromptVersion.prompt_id == prompt_id)
            .order_by(SystemPromptVersion.version.desc())
            .limit(1)
        )
        result = await self.session.execute(stmt)
        current_max = result.scalar_one_or_none() or 0

        # Unset current version flag on all existing versions
        await self.session.execute(
            update(SystemPromptVersion)
            .where(SystemPromptVersion.prompt_id == prompt_id)
            .values(is_current=False)
        )

        # Create new version
        version = SystemPromptVersion(
            prompt_id=prompt_id,
            version=current_max + 1,
            content=content,
            metadata_=metadata or {},
            is_current=True,
        )
        self.session.add(version)

        await self.session.commit()
        await self.session.refresh(version)

        # Invalidate cache
        await prompt_cache.invalidate()

        logger.info("Created version %d for prompt %d", version.version, prompt_id)
        return version

    async def set_current_version(self, version_id: int) -> SystemPromptVersion | None:
        """Set a specific version as current.

        Args:
            version_id: The version ID to set as current

        Returns:
            The updated version or None if not found
        """
        # Get the version
        stmt = select(SystemPromptVersion).where(SystemPromptVersion.id == version_id)
        result = await self.session.execute(stmt)
        version = result.scalar_one_or_none()

        if not version:
            return None

        # Unset current on all versions of this prompt
        await self.session.execute(
            update(SystemPromptVersion)
            .where(SystemPromptVersion.prompt_id == version.prompt_id)
            .values(is_current=False)
        )

        # Set this version as current
        version.is_current = True
        await self.session.commit()
        await self.session.refresh(version)

        # Invalidate cache
        await prompt_cache.invalidate()

        logger.info(
            "Set version %d as current for prompt %d",
            version.version,
            version.prompt_id,
        )
        return version

    async def rollback_to_version(self, version_id: int) -> SystemPromptVersion | None:
        """Rollback to a previous version (same as set_current_version).

        Args:
            version_id: The version ID to rollback to

        Returns:
            The activated version or None if not found
        """
        return await self.set_current_version(version_id)

    async def list_versions(self, prompt_id: int) -> list[SystemPromptVersion]:
        """List all versions of a prompt.

        Args:
            prompt_id: The prompt ID

        Returns:
            List of versions ordered by version number descending
        """
        stmt = (
            select(SystemPromptVersion)
            .where(SystemPromptVersion.prompt_id == prompt_id)
            .order_by(SystemPromptVersion.version.desc())
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def list_prompts(
        self,
        user_scopes: set[str] | None = None,
    ) -> list[SystemPrompt]:
        """List all prompts accessible to the user.

        Args:
            user_scopes: User's scopes for filtering (None = all prompts)

        Returns:
            List of accessible prompts
        """
        stmt = select(SystemPrompt).order_by(SystemPrompt.name)
        result = await self.session.execute(stmt)
        prompts = result.scalars().all()

        if user_scopes is not None:
            return [p for p in prompts if p.is_accessible(user_scopes)]
        return list(prompts)
