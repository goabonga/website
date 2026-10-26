# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Quota management service with support for user and organization ownership."""

from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from knowledge.models import (
    Collection,
    Document,
    Organization,
    PlanType,
    UsageRecord,
    UserPlan,
)
from knowledge.models.enums import OwnerType
from knowledge.services import plan_limits

# Backward compatibility alias
Tenant = Organization


class QuotaExceededError(Exception):
    """Raised when a quota limit is exceeded."""

    def __init__(self, quota_type: str, current: int, limit: int) -> None:
        self.quota_type = quota_type
        self.current = current
        self.limit = limit
        super().__init__(f"Quota exceeded: {quota_type} ({current}/{limit})")


@dataclass
class QuotaStatus:
    """Status of a specific quota."""

    quota_type: str
    current: int
    limit: int
    is_unlimited: bool = False

    @property
    def remaining(self) -> int:
        """Get remaining quota."""
        if self.is_unlimited:
            return -1
        return max(0, self.limit - self.current)

    @property
    def percentage_used(self) -> float:
        """Get percentage of quota used."""
        if self.is_unlimited or self.limit == 0:
            return 0.0
        return min(100.0, (self.current / self.limit) * 100)

    @property
    def is_exceeded(self) -> bool:
        """Check if quota is exceeded."""
        if self.is_unlimited:
            return False
        return self.current >= self.limit

    @property
    def is_near_limit(self) -> bool:
        """Check if quota is near limit (>80%)."""
        return self.percentage_used >= 80.0


@dataclass
class UsageStats:
    """Complete usage statistics for a user or organization."""

    collections: QuotaStatus
    documents_total: QuotaStatus
    api_calls_month: QuotaStatus
    storage_bytes: QuotaStatus
    plan: PlanType


class QuotaService:
    """Service for managing quotas and usage tracking.

    Supports both:
    - Organization-based quotas (legacy, for enterprise)
    - User-based quotas (new, for personal collections)
    """

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    def _content_length_expr(self):
        """Return SQL expression for content byte length by DB dialect."""
        bind = self.db.get_bind()
        dialect = bind.dialect.name if bind is not None else ""
        if dialect == "postgresql":
            return func.octet_length(Document.content)
        return func.length(Document.content)

    async def get_plan_limits(self, plan: PlanType) -> dict[str, int]:
        """Get limits for a plan."""
        return await plan_limits.get_plan_limits(plan.value)

    async def get_limit(self, plan: PlanType, quota_type: str) -> int:
        """Get a specific limit for a plan (0 when the plan does not define it)."""
        limits = await self.get_plan_limits(plan)
        return limits.get(quota_type, 0)

    # =========================================================================
    # Owner-agnostic methods (new polymorphic approach)
    # =========================================================================

    async def get_owner_plan(self, owner_type: OwnerType, owner_id: UUID) -> PlanType:
        """Get the plan for an owner (user or organization).

        Args:
            owner_type: Type of owner (user or organization).
            owner_id: The owner's ID.

        Returns:
            The plan type for the owner.
        """
        if owner_type == OwnerType.USER:
            result = await self.db.execute(select(UserPlan).where(UserPlan.user_id == owner_id))
            user_plan = result.scalar_one_or_none()
            return user_plan.plan if user_plan else PlanType.FREE
        else:
            result = await self.db.execute(select(Organization).where(Organization.id == owner_id))
            org = result.scalar_one_or_none()
            return org.plan if org else PlanType.FREE

    async def get_collection_count_for_owner(self, owner_type: OwnerType, owner_id: UUID) -> int:
        """Get number of collections for an owner.

        Args:
            owner_type: Type of owner (user or organization).
            owner_id: The owner's ID.

        Returns:
            Number of collections owned.
        """
        result = await self.db.execute(
            select(func.count(Collection.id)).where(
                Collection.owner_type == owner_type,
                Collection.owner_id == owner_id,
            )
        )
        return result.scalar() or 0

    async def get_document_count_for_owner(self, owner_type: OwnerType, owner_id: UUID) -> int:
        """Get total number of documents for an owner.

        Args:
            owner_type: Type of owner (user or organization).
            owner_id: The owner's ID.

        Returns:
            Total document count across all owned collections.
        """
        result = await self.db.execute(
            select(func.count(Document.id))
            .join(Collection, Document.collection_id == Collection.id)
            .where(
                Collection.owner_type == owner_type,
                Collection.owner_id == owner_id,
            )
        )
        return result.scalar() or 0

    async def get_storage_bytes_for_owner(self, owner_type: OwnerType, owner_id: UUID) -> int:
        """Get total storage usage in bytes for an owner.

        Args:
            owner_type: Type of owner (user or organization).
            owner_id: The owner's ID.

        Returns:
            Total storage bytes used.
        """
        # Legacy rows can have content_size=0; fallback to content length.
        content_size_expr = case(
            (Document.content_size > 0, Document.content_size),
            else_=func.coalesce(self._content_length_expr(), 0),
        )
        result = await self.db.execute(
            select(
                func.coalesce(
                    func.sum(content_size_expr + func.coalesce(Document.embedding_size, 0)),
                    0,
                )
            )
            .join(Collection, Document.collection_id == Collection.id)
            .where(
                Collection.owner_type == owner_type,
                Collection.owner_id == owner_id,
            )
        )
        return result.scalar() or 0

    async def check_quota_for_owner(
        self, owner_type: OwnerType, owner_id: UUID, quota_type: str
    ) -> QuotaStatus:
        """Check status of a specific quota for an owner.

        Args:
            owner_type: Type of owner (user or organization).
            owner_id: The owner's ID.
            quota_type: The type of quota to check.

        Returns:
            Status of the requested quota.
        """
        plan = await self.get_owner_plan(owner_type, owner_id)
        limit = await self.get_limit(plan, quota_type)
        is_unlimited = limit == plan_limits.UNLIMITED

        if quota_type == "max_collections":
            current = await self.get_collection_count_for_owner(owner_type, owner_id)
        elif quota_type == "max_total_documents":
            current = await self.get_document_count_for_owner(owner_type, owner_id)
        elif quota_type == "max_storage_bytes":
            current = await self.get_storage_bytes_for_owner(owner_type, owner_id)
        else:
            current = 0

        return QuotaStatus(
            quota_type=quota_type,
            current=current,
            limit=limit,
            is_unlimited=is_unlimited,
        )

    async def enforce_quota_for_owner(
        self, owner_type: OwnerType, owner_id: UUID, quota_type: str
    ) -> None:
        """Enforce a quota for an owner, raising QuotaExceededError if exceeded.

        Args:
            owner_type: Type of owner (user or organization).
            owner_id: The owner's ID.
            quota_type: The type of quota to enforce.

        Raises:
            QuotaExceededError: If the quota is exceeded.
        """
        status = await self.check_quota_for_owner(owner_type, owner_id, quota_type)
        if status.is_exceeded:
            raise QuotaExceededError(
                quota_type=quota_type,
                current=status.current,
                limit=status.limit,
            )

    async def enforce_collection_quota_for_owner(
        self, owner_type: OwnerType, owner_id: UUID
    ) -> None:
        """Enforce collection creation quota for an owner.

        Args:
            owner_type: Type of owner (user or organization).
            owner_id: The owner's ID.

        Raises:
            QuotaExceededError: If the collection quota is exceeded.
        """
        await self.enforce_quota_for_owner(owner_type, owner_id, "max_collections")

    async def get_usage_for_owner(self, owner_type: OwnerType, owner_id: UUID) -> UsageStats:
        """Get complete usage statistics for an owner.

        Args:
            owner_type: Type of owner (user or organization).
            owner_id: The owner's ID.

        Returns:
            Complete usage statistics.
        """
        plan = await self.get_owner_plan(owner_type, owner_id)

        collections = await self.check_quota_for_owner(owner_type, owner_id, "max_collections")
        documents = await self.check_quota_for_owner(owner_type, owner_id, "max_total_documents")
        storage = await self.check_quota_for_owner(owner_type, owner_id, "max_storage_bytes")

        # API calls tracked differently - need to implement per-owner tracking
        api_calls_limit = await self.get_limit(plan, "max_api_calls_per_month")
        api_calls = QuotaStatus(
            quota_type="max_api_calls_per_month",
            current=0,
            limit=api_calls_limit,
            is_unlimited=api_calls_limit == plan_limits.UNLIMITED,
        )

        return UsageStats(
            collections=collections,
            documents_total=documents,
            api_calls_month=api_calls,
            storage_bytes=storage,
            plan=plan,
        )

    # =========================================================================
    # Legacy tenant-based methods (for backward compatibility)
    # =========================================================================

    async def get_tenant(self, tenant_id: UUID) -> Organization | None:
        """Get tenant/organization by ID."""
        result = await self.db.execute(select(Organization).where(Organization.id == tenant_id))
        return result.scalar_one_or_none()

    async def get_collection_count(self, tenant_id: UUID) -> int:
        """Get number of collections for a tenant (legacy)."""
        return await self.get_collection_count_for_owner(OwnerType.ORGANIZATION, tenant_id)

    async def get_document_count(self, tenant_id: UUID) -> int:
        """Get total number of documents for a tenant (legacy)."""
        return await self.get_document_count_for_owner(OwnerType.ORGANIZATION, tenant_id)

    async def get_collection_document_count(self, collection_id: UUID) -> int:
        """Get number of documents in a specific collection."""
        result = await self.db.execute(
            select(func.count(Document.id)).where(Document.collection_id == collection_id)
        )
        return result.scalar() or 0

    async def get_storage_bytes(self, tenant_id: UUID) -> int:
        """Get total storage usage in bytes for a tenant (legacy)."""
        return await self.get_storage_bytes_for_owner(OwnerType.ORGANIZATION, tenant_id)

    async def get_api_calls_month(self, tenant_id: UUID) -> int:
        """Get API calls for current month."""
        period = datetime.now(UTC).strftime("%Y-%m")
        result = await self.db.execute(
            select(func.coalesce(func.sum(UsageRecord.value), 0)).where(
                UsageRecord.tenant_id == tenant_id,
                UsageRecord.metric == "api_calls",
                UsageRecord.period == period,
            )
        )
        return result.scalar() or 0

    async def check_quota(self, tenant: Organization, quota_type: str) -> QuotaStatus:
        """Check status of a specific quota (legacy tenant-based)."""
        limit = await self.get_limit(tenant.plan, quota_type)
        is_unlimited = limit == plan_limits.UNLIMITED

        if quota_type == "max_collections":
            current = await self.get_collection_count(tenant.id)
        elif quota_type == "max_total_documents":
            current = await self.get_document_count(tenant.id)
        elif quota_type == "max_api_calls_per_month":
            current = await self.get_api_calls_month(tenant.id)
        elif quota_type == "max_storage_bytes":
            current = await self.get_storage_bytes(tenant.id)
        else:
            current = 0

        return QuotaStatus(
            quota_type=quota_type,
            current=current,
            limit=limit,
            is_unlimited=is_unlimited,
        )

    async def check_collection_document_quota(
        self, tenant: Organization, collection_id: UUID
    ) -> QuotaStatus:
        """Check document quota for a specific collection."""
        limit = await self.get_limit(tenant.plan, "max_documents_per_collection")
        is_unlimited = limit == plan_limits.UNLIMITED
        current = await self.get_collection_document_count(collection_id)

        return QuotaStatus(
            quota_type="max_documents_per_collection",
            current=current,
            limit=limit,
            is_unlimited=is_unlimited,
        )

    async def get_usage(self, tenant_id: UUID) -> UsageStats | None:
        """Get complete usage statistics for a tenant (legacy)."""
        tenant = await self.get_tenant(tenant_id)
        if not tenant:
            return None

        collections = await self.check_quota(tenant, "max_collections")
        documents = await self.check_quota(tenant, "max_total_documents")
        api_calls = await self.check_quota(tenant, "max_api_calls_per_month")
        storage = await self.check_quota(tenant, "max_storage_bytes")

        return UsageStats(
            collections=collections,
            documents_total=documents,
            api_calls_month=api_calls,
            storage_bytes=storage,
            plan=tenant.plan,
        )

    async def enforce_quota(self, tenant: Organization, quota_type: str) -> None:
        """Enforce a quota, raising QuotaExceededError if exceeded (legacy)."""
        status = await self.check_quota(tenant, quota_type)
        if status.is_exceeded:
            raise QuotaExceededError(
                quota_type=quota_type,
                current=status.current,
                limit=status.limit,
            )

    async def enforce_collection_quota(self, tenant: Organization) -> None:
        """Enforce collection creation quota (legacy)."""
        await self.enforce_quota(tenant, "max_collections")

    async def enforce_document_quota(self, tenant: Organization, collection_id: UUID) -> None:
        """Enforce document creation quota (both total and per-collection)."""
        # Check total documents
        await self.enforce_quota(tenant, "max_total_documents")

        # Check per-collection limit
        status = await self.check_collection_document_quota(tenant, collection_id)
        if status.is_exceeded:
            raise QuotaExceededError(
                quota_type="max_documents_per_collection",
                current=status.current,
                limit=status.limit,
            )

    async def enforce_storage_quota(self, tenant: Organization) -> None:
        """Enforce storage quota."""
        await self.enforce_quota(tenant, "max_storage_bytes")

    async def enforce_api_quota(self, tenant: Organization) -> None:
        """Enforce API calls quota."""
        await self.enforce_quota(tenant, "max_api_calls_per_month")

    async def increment_usage(self, tenant_id: UUID, metric: str, value: int = 1) -> None:
        """Increment a usage metric.

        Args:
            tenant_id: The tenant ID.
            metric: The metric name (e.g., "api_calls", "documents_added").
            value: The amount to increment by.
        """
        period = datetime.now(UTC).strftime("%Y-%m")

        # Try to find existing record
        result = await self.db.execute(
            select(UsageRecord).where(
                UsageRecord.tenant_id == tenant_id,
                UsageRecord.metric == metric,
                UsageRecord.period == period,
            )
        )
        record = result.scalar_one_or_none()

        if record:
            record.value += value
        else:
            record = UsageRecord(
                tenant_id=tenant_id,
                metric=metric,
                value=value,
                period=period,
            )
            self.db.add(record)

    async def record_api_call(self, tenant_id: UUID) -> None:
        """Record an API call for the tenant."""
        await self.increment_usage(tenant_id, "api_calls", 1)

    async def record_document_added(self, tenant_id: UUID, count: int = 1) -> None:
        """Record documents added for the tenant."""
        await self.increment_usage(tenant_id, "documents_added", count)

    async def record_search(self, tenant_id: UUID) -> None:
        """Record a search operation for the tenant."""
        await self.increment_usage(tenant_id, "searches", 1)

    async def record_embedding(self, tenant_id: UUID, count: int = 1) -> None:
        """Record embedding generation for the tenant."""
        await self.increment_usage(tenant_id, "embeddings", count)


def format_bytes(size: int | float) -> str:
    """Format bytes to human-readable string."""
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if abs(size) < 1024.0:
            return f"{size:.1f} {unit}"
        size /= 1024.0
    return f"{size:.1f} PB"
