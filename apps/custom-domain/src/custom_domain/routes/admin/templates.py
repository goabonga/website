# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Admin routes for managing nginx templates."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from custom_domain.auth import AuthContext, require_scopes
from custom_domain.config import settings
from custom_domain.database import get_db
from custom_domain.logging import get_logger
from custom_domain.models import CustomDomain, NginxTemplate
from custom_domain.schemas import (
    ReprovisionError,
    TemplateCreate,
    TemplateListItem,
    TemplateListResponse,
    TemplateReprovisionRequest,
    TemplateReprovisionResponse,
    TemplateResponse,
    TemplateUpdate,
    TemplateValidateRequest,
    TemplateValidateResponse,
)
from custom_domain.services import template_service

logger = get_logger(__name__)

router = APIRouter(prefix="/admin/templates", tags=["admin-templates"])

ADMIN_SCOPES = (settings.admin_scope, f"{settings.admin_scope}:templates")


@router.get("", response_model=TemplateListResponse)
async def list_templates(
    db: AsyncSession = Depends(get_db),
    auth: AuthContext = Depends(require_scopes(*ADMIN_SCOPES)),
    client_id: str | None = None,
    shared: bool | None = None,
):
    """List nginx templates.

    ``client_id`` keeps the templates owned by that client; ``shared=true`` keeps the
    shared ones (no owner) and ``shared=false`` the client-owned ones.
    """
    query = select(NginxTemplate).order_by(NginxTemplate.name)
    if client_id is not None:
        query = query.where(NginxTemplate.client_id == client_id)
    if shared is True:
        query = query.where(NginxTemplate.client_id.is_(None))
    elif shared is False:
        query = query.where(NginxTemplate.client_id.isnot(None))
    result = await db.execute(query)
    templates = result.scalars().all()

    # Get domain counts
    items: list[TemplateListItem] = []
    for template in templates:
        count_query = select(func.count()).where(CustomDomain.nginx_template_id == template.id)
        domains_count = await db.scalar(count_query) or 0

        item = TemplateListItem(
            id=template.id,
            slug=template.slug,
            name=template.name,
            description=template.description,
            client_id=template.client_id,
            is_default=template.is_default,
            is_active=template.is_active,
            domains_count=domains_count,
            available_variables=template.available_variables or [],
            created_at=template.created_at,
        )
        items.append(item)

    return TemplateListResponse(
        items=items,
        total=len(items),
    )


@router.post("", response_model=TemplateResponse, status_code=status.HTTP_201_CREATED)
async def create_template(
    data: TemplateCreate,
    db: AsyncSession = Depends(get_db),
    auth: AuthContext = Depends(require_scopes(*ADMIN_SCOPES)),
):
    """Create a new nginx template."""
    # Check if slug already exists
    existing = await db.execute(select(NginxTemplate).where(NginxTemplate.slug == data.slug))
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Template slug already exists",
        )

    # Validate templates
    http_result = template_service.validate_template(data.http_template)
    if not http_result.valid:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid HTTP template: {http_result.errors}",
        )

    https_result = template_service.validate_template(data.https_template)
    if not https_result.valid:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid HTTPS template: {https_result.errors}",
        )

    template = NginxTemplate(
        slug=data.slug,
        name=data.name,
        description=data.description,
        client_id=data.client_id,
        http_template=data.http_template,
        https_template=data.https_template,
        available_variables=data.available_variables,
        is_default=False,
        is_active=True,
    )

    db.add(template)
    await db.commit()
    await db.refresh(template)

    logger.info("Template created: %s", template.slug)

    return TemplateResponse.model_validate(template)


@router.get("/{template_id}", response_model=TemplateResponse)
async def get_template(
    template_id: int,
    db: AsyncSession = Depends(get_db),
    auth: AuthContext = Depends(require_scopes(*ADMIN_SCOPES)),
):
    """Get template details."""
    result = await db.execute(select(NginxTemplate).where(NginxTemplate.id == template_id))
    template = result.scalar_one_or_none()

    if not template:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Template not found",
        )

    return TemplateResponse.model_validate(template)


@router.put("/{template_id}", response_model=TemplateResponse)
async def update_template(
    template_id: int,
    data: TemplateUpdate,
    db: AsyncSession = Depends(get_db),
    auth: AuthContext = Depends(require_scopes(*ADMIN_SCOPES)),
):
    """Update a template."""
    result = await db.execute(select(NginxTemplate).where(NginxTemplate.id == template_id))
    template = result.scalar_one_or_none()

    if not template:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Template not found",
        )

    update_data = data.model_dump(exclude_unset=True)

    # Validate new templates if provided
    if "http_template" in update_data:
        http_validation = template_service.validate_template(update_data["http_template"])
        if not http_validation.valid:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid HTTP template: {http_validation.errors}",
            )

    if "https_template" in update_data:
        https_validation = template_service.validate_template(update_data["https_template"])
        if not https_validation.valid:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid HTTPS template: {https_validation.errors}",
            )

    for field, value in update_data.items():
        setattr(template, field, value)

    await db.commit()
    await db.refresh(template)

    logger.info("Template updated: %s", template.slug)

    return TemplateResponse.model_validate(template)


@router.delete("/{template_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_template(
    template_id: int,
    db: AsyncSession = Depends(get_db),
    auth: AuthContext = Depends(require_scopes(*ADMIN_SCOPES)),
):
    """Delete a template."""
    result = await db.execute(select(NginxTemplate).where(NginxTemplate.id == template_id))
    template = result.scalar_one_or_none()

    if not template:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Template not found",
        )

    if template.is_default:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot delete the default template",
        )

    # Check for domains using this template
    count_query = select(func.count()).where(CustomDomain.nginx_template_id == template.id)
    domains_count = await db.scalar(count_query) or 0

    if domains_count > 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot delete template with {domains_count} associated domains",
        )

    await db.delete(template)
    await db.commit()

    logger.info("Template deleted: %s", template.slug)


@router.post("/{template_id}/validate", response_model=TemplateValidateResponse)
async def validate_template(
    template_id: int,
    data: TemplateValidateRequest,
    db: AsyncSession = Depends(get_db),
    auth: AuthContext = Depends(require_scopes(*ADMIN_SCOPES)),
):
    """Validate a template with test variables."""
    result = await db.execute(select(NginxTemplate).where(NginxTemplate.id == template_id))
    template = result.scalar_one_or_none()

    if not template:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Template not found",
        )

    errors = []
    rendered_http = None
    rendered_https = None
    nginx_valid = False

    # Validate HTTP template
    http_result = template_service.validate_template(
        template.http_template,
        data.test_variables,
    )
    if not http_result.valid:
        errors.extend(http_result.errors)
    else:
        rendered_http = http_result.rendered_output

    # Validate HTTPS template
    https_result = template_service.validate_template(
        template.https_template,
        data.test_variables,
    )
    if not https_result.valid:
        errors.extend(https_result.errors)
    else:
        rendered_https = https_result.rendered_output

    # Validate nginx syntax if both rendered
    if rendered_http and rendered_https:
        full_config = f"{rendered_http}\n\n{rendered_https}"
        nginx_valid, nginx_error = await template_service.validate_nginx_syntax_in_worker(
            full_config
        )
        if not nginx_valid:
            errors.append(f"Nginx syntax error: {nginx_error}")

    return TemplateValidateResponse(
        valid=len(errors) == 0,
        rendered_http=rendered_http,
        rendered_https=rendered_https,
        nginx_syntax_valid=nginx_valid,
        errors=errors,
    )


@router.post("/{template_id}/set-default", response_model=TemplateResponse)
async def set_default_template(
    template_id: int,
    db: AsyncSession = Depends(get_db),
    auth: AuthContext = Depends(require_scopes(*ADMIN_SCOPES)),
):
    """Set a template as the default."""
    result = await db.execute(select(NginxTemplate).where(NginxTemplate.id == template_id))
    template = result.scalar_one_or_none()

    if not template:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Template not found",
        )

    if template.client_id is not None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="A client-owned template can not be the global default",
        )

    # Unset current default
    await db.execute(
        select(NginxTemplate).where(NginxTemplate.is_default == True)  # noqa: E712
    )
    current_defaults = (
        (
            await db.execute(
                select(NginxTemplate).where(NginxTemplate.is_default == True)  # noqa: E712
            )
        )
        .scalars()
        .all()
    )

    for t in current_defaults:
        t.is_default = False

    # Set new default
    template.is_default = True
    await db.commit()
    await db.refresh(template)

    logger.info("Default template set: %s", template.slug)

    return TemplateResponse.model_validate(template)


@router.post("/{template_id}/reprovision", response_model=TemplateReprovisionResponse)
async def reprovision_domains(
    template_id: int,
    data: TemplateReprovisionRequest,
    db: AsyncSession = Depends(get_db),
    auth: AuthContext = Depends(require_scopes(*ADMIN_SCOPES)),
):
    """Reprovision all domains using this template."""
    result = await db.execute(select(NginxTemplate).where(NginxTemplate.id == template_id))
    template = result.scalar_one_or_none()

    if not template:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Template not found",
        )

    # Get domains using this template
    query = select(CustomDomain).where(CustomDomain.nginx_template_id == template.id)

    if data.only_active:
        query = query.where(CustomDomain.status == "active")

    domains = (await db.execute(query)).scalars().all()

    if data.dry_run:
        return TemplateReprovisionResponse(
            domains_affected=len(domains),
            success=len(domains),
            failed=0,
            errors=[],
        )

    # Trigger reprovisioning tasks
    success = 0
    failed = 0
    errors: list[ReprovisionError] = []

    for domain in domains:
        try:
            from custom_domain.tasks import provision_domain_ssl

            provision_domain_ssl.delay(str(domain.id))
            success += 1
        except Exception as e:
            failed += 1
            errors.append(ReprovisionError(domain=domain.domain, error=str(e)))

    logger.info(
        "Reprovisioning triggered for template %s: %d domains",
        template.slug,
        len(domains),
    )

    return TemplateReprovisionResponse(
        domains_affected=len(domains),
        success=success,
        failed=failed,
        errors=errors,
    )
