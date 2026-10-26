# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Email template CRUD routes."""

import math
import re

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from mailler.auth import AuthContext, require_scopes
from mailler.database import get_db
from mailler.logging import get_logger
from mailler.models.template import EmailTemplate, TemplateStatus
from mailler.schemas.template import (
    CompileRequest,
    CompileResponse,
    RenderRequest,
    RenderResponse,
    TemplateCreate,
    TemplateListItem,
    TemplateListResponse,
    TemplateResponse,
    TemplateUpdate,
)
from mailler.services.mjml import compile_mjml
from mailler.services.rendering import RenderError, render_parts

logger = get_logger(__name__)

router = APIRouter(prefix="/templates", tags=["Templates"])


def extract_variables(mjml_source: str, subject_template: str) -> list[str]:
    """Extract Jinja2 variable names from template source.

    Args:
        mjml_source: MJML template source
        subject_template: Subject line template

    Returns:
        List of unique variable names found
    """
    combined = mjml_source + " " + subject_template
    # Match {{ variable_name }} and {{ variable_name.attribute }}
    pattern = r"\{\{\s*([a-zA-Z_][a-zA-Z0-9_]*)"
    matches = re.findall(pattern, combined)
    # Return unique variables, preserving order
    seen: set[str] = set()
    result: list[str] = []
    for v in matches:
        if v not in seen:
            seen.add(v)
            result.append(v)
    return result


@router.get("", response_model=TemplateListResponse)
async def list_templates(
    page: int = Query(default=1, ge=1, description="Page number"),
    page_size: int = Query(default=20, ge=1, le=100, description="Items per page"),
    status: str | None = Query(default=None, description="Filter by status"),
    search: str | None = Query(default=None, description="Search in name and slug"),
    client_id: str | None = Query(
        default=None, description="Administrators only: restrict to one client"
    ),
    db: AsyncSession = Depends(get_db),
    auth: AuthContext = Depends(require_scopes("mailler:read")),
) -> TemplateListResponse:
    """List the email templates of the calling client with pagination.

    Administrators see the templates of every client.

    Args:
        page: Page number (1-indexed)
        page_size: Items per page
        status: Optional status filter (draft, active, archived)
        search: Optional search term
        client_id: Optional client filter, honoured for administrators only
        db: Database session
        auth: Authentication context

    Returns:
        Paginated list of templates
    """
    # Build query
    stmt = auth.restrict(select(EmailTemplate), EmailTemplate.client_id, client_id).order_by(
        EmailTemplate.updated_at.desc()
    )

    if status:
        stmt = stmt.where(EmailTemplate.status == status)
    if search:
        search_pattern = f"%{search}%"
        stmt = stmt.where(
            (EmailTemplate.name.ilike(search_pattern)) | (EmailTemplate.slug.ilike(search_pattern))
        )

    # Get total count
    count_stmt = auth.restrict(
        select(func.count(EmailTemplate.id)), EmailTemplate.client_id, client_id
    )
    if status:
        count_stmt = count_stmt.where(EmailTemplate.status == status)
    if search:
        count_stmt = count_stmt.where(
            (EmailTemplate.name.ilike(search_pattern)) | (EmailTemplate.slug.ilike(search_pattern))
        )

    total = (await db.execute(count_stmt)).scalar() or 0
    pages = math.ceil(total / page_size) if total > 0 else 1

    # Get page
    offset = (page - 1) * page_size
    stmt = stmt.offset(offset).limit(page_size)
    result = await db.execute(stmt)
    templates = result.scalars().all()

    items = [
        TemplateListItem(
            id=t.id,
            client_id=t.client_id,
            slug=t.slug,
            name=t.name,
            description=t.description,
            status=t.status,
            variables=t.variables,
            created_at=t.created_at,
            updated_at=t.updated_at,
        )
        for t in templates
    ]

    return TemplateListResponse(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
        pages=pages,
    )


@router.post("", response_model=TemplateResponse, status_code=201)
async def create_template(
    request: TemplateCreate,
    db: AsyncSession = Depends(get_db),
    auth: AuthContext = Depends(require_scopes("mailler:write")),
) -> TemplateResponse:
    """Create a new email template.

    Args:
        request: Template data
        db: Database session
        auth: Authentication context

    Returns:
        Created template

    Raises:
        HTTPException: If slug already exists for the client or MJML compilation fails
    """
    owner = auth.target_client_id(request.client_id)

    # Compile MJML to HTML
    compile_result = await compile_mjml(request.mjml_source)
    if compile_result.get("errors"):
        raise HTTPException(
            status_code=400,
            detail=f"MJML compilation failed: {compile_result['errors']}",
        )

    # Extract variables if not provided
    variables = request.variables
    if variables is None:
        variables = extract_variables(request.mjml_source, request.subject_template)

    template = EmailTemplate(
        client_id=owner,
        slug=request.slug,
        name=request.name,
        description=request.description,
        subject_template=request.subject_template,
        mjml_source=request.mjml_source,
        html_compiled=compile_result.get("html"),
        plain_text=request.plain_text,
        status=TemplateStatus.DRAFT.value,
        variables=variables,
        metadata_=request.metadata or {},
    )

    try:
        db.add(template)
        await db.commit()
        await db.refresh(template)
    except IntegrityError:
        await db.rollback()
        raise HTTPException(
            status_code=409,
            detail=f"Template with slug '{request.slug}' already exists for this client",
        )

    logger.info(
        "Template created",
        extra={
            "template_id": template.id,
            "slug": template.slug,
            "user_id": str(auth.user.id) if auth.user.id else None,
        },
    )

    return TemplateResponse(
        id=template.id,
        client_id=template.client_id,
        slug=template.slug,
        name=template.name,
        description=template.description,
        subject_template=template.subject_template,
        mjml_source=template.mjml_source,
        html_compiled=template.html_compiled,
        plain_text=template.plain_text,
        status=template.status,
        variables=template.variables,
        metadata=template.metadata_,
        created_at=template.created_at,
        updated_at=template.updated_at,
    )


@router.get("/{template_id}", response_model=TemplateResponse)
async def get_template(
    template_id: int,
    db: AsyncSession = Depends(get_db),
    auth: AuthContext = Depends(require_scopes("mailler:read")),
) -> TemplateResponse:
    """Get email template by ID.

    A template of another client is reported as not found.

    Args:
        template_id: Template ID
        db: Database session
        auth: Authentication context

    Returns:
        Template details

    Raises:
        HTTPException: If template not found
    """
    template = await db.get(EmailTemplate, template_id)
    if not template or not auth.owns(template.client_id):
        raise HTTPException(status_code=404, detail="Template not found")

    return TemplateResponse(
        id=template.id,
        client_id=template.client_id,
        slug=template.slug,
        name=template.name,
        description=template.description,
        subject_template=template.subject_template,
        mjml_source=template.mjml_source,
        html_compiled=template.html_compiled,
        plain_text=template.plain_text,
        status=template.status,
        variables=template.variables,
        metadata=template.metadata_,
        created_at=template.created_at,
        updated_at=template.updated_at,
    )


@router.get("/by-slug/{slug}", response_model=TemplateResponse)
async def get_template_by_slug(
    slug: str,
    client_id: str | None = Query(
        default=None, description="Administrators only: client owning the template"
    ),
    db: AsyncSession = Depends(get_db),
    auth: AuthContext = Depends(require_scopes("mailler:read")),
) -> TemplateResponse:
    """Get an email template of the calling client by slug.

    Slugs are unique per client only, so the lookup is always made inside one
    client: the caller's own, or the one an administrator names.

    Args:
        slug: Template slug
        client_id: Client owning the template, administrators only
        db: Database session
        auth: Authentication context

    Returns:
        Template details

    Raises:
        HTTPException: If template not found
    """
    stmt = select(EmailTemplate).where(
        EmailTemplate.slug == slug,
        EmailTemplate.client_id == auth.target_client_id(client_id),
    )
    result = await db.execute(stmt)
    template = result.scalar_one_or_none()

    if not template:
        raise HTTPException(status_code=404, detail="Template not found")

    return TemplateResponse(
        id=template.id,
        client_id=template.client_id,
        slug=template.slug,
        name=template.name,
        description=template.description,
        subject_template=template.subject_template,
        mjml_source=template.mjml_source,
        html_compiled=template.html_compiled,
        plain_text=template.plain_text,
        status=template.status,
        variables=template.variables,
        metadata=template.metadata_,
        created_at=template.created_at,
        updated_at=template.updated_at,
    )


@router.put("/{template_id}", response_model=TemplateResponse)
async def update_template(
    template_id: int,
    request: TemplateUpdate,
    db: AsyncSession = Depends(get_db),
    auth: AuthContext = Depends(require_scopes("mailler:write")),
) -> TemplateResponse:
    """Update an email template.

    Args:
        template_id: Template ID
        request: Updated template data
        db: Database session
        auth: Authentication context

    Returns:
        Updated template

    Raises:
        HTTPException: If template not found or MJML compilation fails
    """
    template = await db.get(EmailTemplate, template_id)
    if not template or not auth.owns(template.client_id):
        raise HTTPException(status_code=404, detail="Template not found")

    # Update fields if provided
    if request.name is not None:
        template.name = request.name
    if request.description is not None:
        template.description = request.description
    if request.subject_template is not None:
        template.subject_template = request.subject_template
    if request.plain_text is not None:
        template.plain_text = request.plain_text
    if request.metadata is not None:
        template.metadata_ = request.metadata
    if request.status is not None:
        template.status = request.status

    # Recompile MJML if source changed
    if request.mjml_source is not None:
        compile_result = await compile_mjml(request.mjml_source)
        if compile_result.get("errors"):
            raise HTTPException(
                status_code=400,
                detail=f"MJML compilation failed: {compile_result['errors']}",
            )
        template.mjml_source = request.mjml_source
        template.html_compiled = compile_result.get("html")

    # Update variables
    if request.variables is not None:
        template.variables = request.variables
    elif request.mjml_source is not None or request.subject_template is not None:
        # Re-extract variables if source or subject changed
        template.variables = extract_variables(template.mjml_source, template.subject_template)

    await db.commit()
    await db.refresh(template)

    logger.info(
        "Template updated",
        extra={
            "template_id": template.id,
            "slug": template.slug,
            "user_id": str(auth.user.id) if auth.user.id else None,
        },
    )

    return TemplateResponse(
        id=template.id,
        client_id=template.client_id,
        slug=template.slug,
        name=template.name,
        description=template.description,
        subject_template=template.subject_template,
        mjml_source=template.mjml_source,
        html_compiled=template.html_compiled,
        plain_text=template.plain_text,
        status=template.status,
        variables=template.variables,
        metadata=template.metadata_,
        created_at=template.created_at,
        updated_at=template.updated_at,
    )


@router.delete("/{template_id}", status_code=204)
async def delete_template(
    template_id: int,
    db: AsyncSession = Depends(get_db),
    auth: AuthContext = Depends(require_scopes("mailler:write")),
) -> None:
    """Delete an email template.

    Args:
        template_id: Template ID
        db: Database session
        auth: Authentication context

    Raises:
        HTTPException: If template not found
    """
    template = await db.get(EmailTemplate, template_id)
    if not template or not auth.owns(template.client_id):
        raise HTTPException(status_code=404, detail="Template not found")

    logger.info(
        "Template deleted",
        extra={
            "template_id": template.id,
            "slug": template.slug,
            "user_id": str(auth.user.id) if auth.user.id else None,
        },
    )

    await db.delete(template)
    await db.commit()


@router.post("/compile", response_model=CompileResponse)
async def compile_mjml_endpoint(
    request: CompileRequest,
    _auth: AuthContext = Depends(require_scopes("mailler:read")),
) -> CompileResponse:
    """Compile MJML to HTML without saving.

    Args:
        request: MJML source code
        _auth: Authentication context

    Returns:
        Compiled HTML and any warnings
    """
    result = await compile_mjml(request.mjml_source)
    return CompileResponse(
        html=result.get("html", ""),
        errors=result.get("errors"),
    )


@router.post("/{template_id}/render", response_model=RenderResponse)
async def render_template(
    template_id: int,
    request: RenderRequest,
    db: AsyncSession = Depends(get_db),
    auth: AuthContext = Depends(require_scopes("mailler:read")),
) -> RenderResponse:
    """Render a template with provided variables.

    Args:
        template_id: Template ID
        request: Variables to render
        db: Database session
        auth: Authentication context

    Returns:
        Rendered subject, HTML, and plain text

    Raises:
        HTTPException: If template not found or rendering fails
    """
    template = await db.get(EmailTemplate, template_id)
    if not template or not auth.owns(template.client_id):
        raise HTTPException(status_code=404, detail="Template not found")

    if not template.html_compiled:
        raise HTTPException(status_code=400, detail="Template has not been compiled yet")

    try:
        rendered = render_parts(
            subject_template=template.subject_template,
            html_compiled=template.html_compiled,
            plain_text=template.plain_text,
            variables=request.variables,
        )
    except RenderError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return RenderResponse(
        subject=rendered.subject,
        html=rendered.html,
        plain_text=rendered.plain_text,
    )
