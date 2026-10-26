# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Domain CRUD endpoints."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from custom_domain.auth import AuthContext
from custom_domain.config import settings
from custom_domain.database import get_db
from custom_domain.logging import get_logger
from custom_domain.models import CustomDomain, DomainStatus
from custom_domain.routes.access import require_client_scopes
from custom_domain.schemas import (
    DomainActionResponse,
    DomainCreate,
    DomainCreateResponse,
    DomainListItem,
    DomainListResponse,
    DomainLookupResponse,
    DomainResponse,
    DomainUpdate,
)
from custom_domain.services import domain_service, template_service
from custom_domain.services.upstream import InvalidUpstreamError, parse_upstream

logger = get_logger(__name__)

router = APIRouter(prefix="/domains", tags=["domains"])


async def get_domain_or_404(
    db: AsyncSession,
    domain_id: UUID,
    auth: AuthContext,
    include_deleted: bool = False,
) -> CustomDomain:
    """Get a domain by ID or raise 404."""
    query = select(CustomDomain).where(CustomDomain.id == domain_id)

    # Exclude soft-deleted unless explicitly requested
    if not include_deleted:
        query = query.where(CustomDomain.deleted_at.is_(None))

    result = await db.execute(query)
    domain = result.scalar_one_or_none()

    if not domain:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Domain not found",
        )

    # Check ownership (unless admin)
    if not auth.is_admin and domain.client_id != auth.user.client_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied",
        )

    return domain


async def ensure_template_usable(db: AsyncSession, template_id: int, client_id: str) -> None:
    """Refuse a template that does not exist or belongs to another client.

    A client may use the shared templates and the ones it owns.

    Raises:
        HTTPException: 400 when the template is not available to the client
    """
    if not await template_service.get_usable_template(db, template_id, client_id):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Nginx template not found or not available to this client",
        )


@router.get("", response_model=DomainListResponse)
async def list_domains(
    status_filter: DomainStatus | None = None,
    owner_id: str | None = None,
    include_deleted: bool = False,
    limit: int = 20,
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
    auth: AuthContext = Depends(require_client_scopes("custom-domain:read")),
):
    """List domains for the authenticated client."""
    query = select(CustomDomain)

    # Exclude soft-deleted by default
    if not include_deleted:
        query = query.where(CustomDomain.deleted_at.is_(None))

    # Filter by client unless admin
    if not auth.is_admin:
        query = query.where(CustomDomain.client_id == auth.user.client_id)

    if status_filter:
        query = query.where(CustomDomain.status == status_filter)

    if owner_id:
        query = query.where(CustomDomain.owner_id == owner_id)

    # Get total count
    count_query = select(func.count()).select_from(query.subquery())
    total = await db.scalar(count_query)

    # Get paginated results
    query = query.order_by(CustomDomain.created_at.desc())
    query = query.offset(offset).limit(limit)
    result = await db.execute(query)
    domains = result.scalars().all()

    items = [DomainListItem.model_validate(d) for d in domains]
    return DomainListResponse(
        items=items,
        total=total or 0,
        limit=limit,
        offset=offset,
    )


@router.post("", response_model=DomainCreateResponse, status_code=status.HTTP_201_CREATED)
async def create_domain(
    data: DomainCreate,
    db: AsyncSession = Depends(get_db),
    auth: AuthContext = Depends(require_client_scopes("custom-domain:write")),
):
    """Register a new custom domain."""
    # Validate domain name
    is_valid, error = domain_service.validate_domain_name(data.domain)
    if not is_valid:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=error,
        )

    # Check if domain already exists (only non-deleted)
    existing = await db.execute(
        select(CustomDomain).where(
            CustomDomain.domain == data.domain.lower(),
            CustomDomain.deleted_at.is_(None),
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Domain already registered",
        )

    # Get client configuration
    if not auth.user.client_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Client ID required",
        )
    client = await domain_service.get_authorized_client(db, auth.user.client_id)
    if not client:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Client not authorized",
        )

    # Check domain limit (only count non-deleted domains)
    if client.max_domains:
        count_query = select(func.count()).where(
            CustomDomain.client_id == auth.user.client_id,
            CustomDomain.deleted_at.is_(None),
        )
        current_count = await db.scalar(count_query)
        if current_count and current_count >= client.max_domains:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Domain limit reached ({client.max_domains})",
            )

    # Resolve the targets: the request, then the client's defaults, then the settings
    upstream_target = data.upstream_target or client.default_upstream_target
    if not upstream_target:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No upstream target: provide one or set a default for the client",
        )
    try:
        parse_upstream(upstream_target)
    except InvalidUpstreamError as error:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid upstream target: {error}",
        ) from error
    cname_target = data.cname_target or client.default_cname_target or settings.default_cname_target
    if not cname_target:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No CNAME target: provide one or set a default for the client",
        )

    if data.nginx_template_id is not None:
        await ensure_template_usable(db, data.nginx_template_id, auth.user.client_id)

    # Create domain
    domain = CustomDomain(
        domain=data.domain.lower(),
        client_id=auth.user.client_id,
        owner_id=data.owner_id,
        owner_type=data.owner_type,
        upstream_target=upstream_target,
        cname_target=cname_target,
        nginx_template_id=data.nginx_template_id,
        metadata_=data.metadata,
        status=DomainStatus.PENDING,
    )

    db.add(domain)
    await db.commit()
    await db.refresh(domain)

    logger.info(
        "Domain created: %s for client %s",
        domain.domain,
        auth.user.client_id,
    )

    # Trigger DNS verification task
    from custom_domain.tasks import verify_domain_dns

    verify_domain_dns.delay(str(domain.id))

    return DomainCreateResponse(
        id=domain.id,
        domain=domain.domain,
        status=domain.status,
        cname_target=domain.cname_target,
        owner_id=domain.owner_id,
        owner_type=domain.owner_type,
        created_at=domain.created_at,
        dns_instructions=f"Create a CNAME record pointing {domain.domain} to {domain.cname_target}",
    )


@router.get("/lookup/{domain_name}", response_model=DomainLookupResponse)
async def lookup_domain(
    domain_name: str,
    db: AsyncSession = Depends(get_db),
    auth: AuthContext = Depends(require_client_scopes("custom-domain:lookup")),
):
    """Lookup an active domain by name (for middleware).

    A client only sees its own domains: a name registered by another client is
    answered like an unknown one. Holders of the administration scope see all.
    """
    query = select(CustomDomain).where(
        CustomDomain.domain == domain_name.lower(),
        CustomDomain.status == DomainStatus.ACTIVE,
        CustomDomain.deleted_at.is_(None),
    )
    if not auth.is_admin:
        query = query.where(CustomDomain.client_id == auth.user.client_id)
    result = await db.execute(query)
    domain = result.scalar_one_or_none()

    if not domain:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Domain not found or not active",
        )

    return DomainLookupResponse(
        domain=domain.domain,
        owner_id=domain.owner_id,
        owner_type=domain.owner_type,
        client_id=domain.client_id,
        status=domain.status,
        metadata=domain.metadata_,
    )


@router.get("/{domain_id}", response_model=DomainResponse)
async def get_domain(
    domain_id: UUID,
    db: AsyncSession = Depends(get_db),
    auth: AuthContext = Depends(require_client_scopes("custom-domain:read")),
):
    """Get domain details."""
    domain = await get_domain_or_404(db, domain_id, auth)
    return DomainResponse.model_validate(domain)


@router.put("/{domain_id}", response_model=DomainResponse)
async def update_domain(
    domain_id: UUID,
    data: DomainUpdate,
    db: AsyncSession = Depends(get_db),
    auth: AuthContext = Depends(require_client_scopes("custom-domain:write")),
):
    """Update a domain."""
    domain = await get_domain_or_404(db, domain_id, auth)

    if domain.status == DomainStatus.DEPROVISIONING:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Domain is being deleted",
        )

    if data.upstream_target is not None:
        domain.upstream_target = data.upstream_target

    if data.nginx_template_id is not None:
        await ensure_template_usable(db, data.nginx_template_id, domain.client_id)
        domain.nginx_template_id = data.nginx_template_id

    if data.metadata is not None:
        domain.metadata_ = data.metadata

    await db.commit()
    await db.refresh(domain)

    return DomainResponse.model_validate(domain)


@router.delete(
    "/{domain_id}",
    response_model=DomainActionResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def delete_domain(
    domain_id: UUID,
    db: AsyncSession = Depends(get_db),
    auth: AuthContext = Depends(require_client_scopes("custom-domain:write")),
):
    """Delete a domain.

    The API process has no privileges: it only marks the domain ``deprovisioning``
    and queues the work. A worker removes the nginx configuration, revokes the
    certificate and soft-deletes the domain; until then the domain is still
    returned (status ``deprovisioning``) and its name can not be registered again.
    Repeating the request queues the work again, which is harmless.
    """
    domain = await get_domain_or_404(db, domain_id, auth)

    domain.status = DomainStatus.DEPROVISIONING
    domain.error_message = "Deleted by user"
    await db.commit()

    from custom_domain.tasks import deprovision_domain

    deprovision_domain.delay(str(domain.id))

    logger.info("Domain deletion requested: %s", domain.domain)

    return DomainActionResponse(
        id=domain.id,
        status=domain.status,
        message="Deprovisioning started",
    )


@router.post("/{domain_id}/verify", response_model=DomainActionResponse)
async def verify_domain(
    domain_id: UUID,
    db: AsyncSession = Depends(get_db),
    auth: AuthContext = Depends(require_client_scopes("custom-domain:write")),
):
    """Trigger DNS verification for a domain."""
    domain = await get_domain_or_404(db, domain_id, auth)

    if domain.status not in (
        DomainStatus.PENDING,
        DomainStatus.FAILED,
        DomainStatus.DNS_VERIFYING,
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot verify domain in status {domain.status}",
        )

    # Reset retry count and trigger verification
    domain.status = DomainStatus.DNS_VERIFYING
    domain.retry_count = 0
    await db.commit()

    from custom_domain.tasks import verify_domain_dns

    verify_domain_dns.delay(str(domain.id))

    return DomainActionResponse(
        id=domain.id,
        status=domain.status,
        message="DNS verification started",
    )


@router.post("/{domain_id}/provision", response_model=DomainActionResponse)
async def provision_domain(
    domain_id: UUID,
    db: AsyncSession = Depends(get_db),
    auth: AuthContext = Depends(require_client_scopes("custom-domain:write")),
):
    """Trigger SSL provisioning for a domain."""
    domain = await get_domain_or_404(db, domain_id, auth)

    if domain.status not in (
        DomainStatus.DNS_VERIFIED,
        DomainStatus.FAILED,
        DomainStatus.ACTIVE,
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot provision domain in status {domain.status}",
        )

    domain.status = DomainStatus.SSL_PROVISIONING
    await db.commit()

    from custom_domain.tasks import provision_domain_ssl

    provision_domain_ssl.delay(str(domain.id))

    return DomainActionResponse(
        id=domain.id,
        status=domain.status,
        message="SSL provisioning started",
    )
