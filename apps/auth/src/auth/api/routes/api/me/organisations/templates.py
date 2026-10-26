# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""User-scoped organisation template management API endpoints."""

import logging
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from auth.api.deps import get_db
from auth.api.routes.api.deps import get_current_user_bearer, require_org_membership
from auth.api.schemas.api.organisations import (
    TemplateResponse,
    UpdateTemplateRequest,
)
from auth.db.models.user import User
from auth.services.tenant import tenant_service as _tenant_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/templates", tags=["me-organisations:templates"])


@router.get("/", response_model=list[TemplateResponse])
async def list_templates(
    org_id: uuid.UUID,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user_bearer)],
) -> list[TemplateResponse]:
    """List all custom templates for an organisation.

    Returns all per-tenant Jinja2/MJML template overrides stored for the
    organisation, ordered by template name. Templates not present here fall
    back to the server-side default templates.

    **Required scope:** org membership + `templates:read`

    **Example:**
    ```
    curl -H "Authorization: Bearer <token>" \\
      https://auth.example.com/api/v1/me/organisations/550e8400-e29b-41d4-a716-446655440000/templates/
    ```
    """
    _user, tenant, _membership = await require_org_membership(
        org_id, request, db, user, required_scope="templates:read"
    )

    templates = await _tenant_service.list_templates(db, tenant.id)
    return [TemplateResponse.model_validate(t) for t in templates]


@router.get("/{template_name:path}", response_model=TemplateResponse)
async def get_template(
    org_id: uuid.UUID,
    template_name: str,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user_bearer)],
) -> TemplateResponse:
    """Retrieve a single custom template by name for an organisation.

    Returns the stored Jinja2/MJML template override for the given
    `template_name`. Raises 404 if no override exists for the name; the
    caller should then fall back to the server-side default.

    **Required scope:** org membership + `templates:read`

    **Example:**
    ```
    curl -H "Authorization: Bearer <token>" \\
      https://auth.example.com/api/v1/me/organisations/550e8400-e29b-41d4-a716-446655440000/templates/emails/welcome.mjml
    ```
    """
    _user, tenant, _membership = await require_org_membership(
        org_id, request, db, user, required_scope="templates:read"
    )

    template = await _tenant_service.get_template(db, tenant.id, template_name)
    if not template:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Template not found",
        )

    return TemplateResponse.model_validate(template)


@router.put("/{template_name:path}", response_model=TemplateResponse)
async def update_template(
    org_id: uuid.UUID,
    template_name: str,
    body: UpdateTemplateRequest,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user_bearer)],
) -> TemplateResponse:
    """Create or replace a custom template override for an organisation.

    Upserts the Jinja2/MJML template identified by `template_name`. If an
    override already exists it is fully replaced; otherwise a new one is
    created. Once saved, the template is served in place of the server-side
    default for every render within the organisation.

    **Required scope:** org membership + `templates:write`

    **Example:**
    ```
    curl -X PUT \\
      -H "Authorization: Bearer <token>" \\
      -H "Content-Type: application/json" \\
      -d '{"content": "{% block body %}Hello {{ user.name }}{% endblock %}", "description": "Custom welcome email", "is_active": true}' \\
      https://auth.example.com/api/v1/me/organisations/550e8400-e29b-41d4-a716-446655440000/templates/emails/welcome.mjml
    ```
    """
    _user, tenant, _membership = await require_org_membership(
        org_id, request, db, user, required_scope="templates:write"
    )

    template = await _tenant_service.upsert_template(
        db,
        tenant.id,
        template_name,
        content=body.content,
        description=body.description,
        is_active=body.is_active,
    )

    await db.commit()
    await db.refresh(template)

    logger.info(
        "ACTION: me_template_update, user_id=%s, tenant_id=%s, template=%s",
        user.id,
        tenant.id,
        template_name,
    )

    return TemplateResponse.model_validate(template)


@router.post("/{template_name:path}/toggle", response_model=TemplateResponse)
async def toggle_template(
    org_id: uuid.UUID,
    template_name: str,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user_bearer)],
) -> TemplateResponse:
    """Toggle the active state of a custom template override for an organisation.

    Flips the `is_active` flag on the named template override. When set to
    inactive the organisation falls back to the server-side default for that
    template name, without deleting the stored override. Raises 404 if no
    override exists for the name.

    **Required scope:** org membership + `templates:write`

    **Example:**
    ```
    curl -X POST \\
      -H "Authorization: Bearer <token>" \\
      https://auth.example.com/api/v1/me/organisations/550e8400-e29b-41d4-a716-446655440000/templates/emails/welcome.mjml/toggle
    ```
    """
    _user, tenant, _membership = await require_org_membership(
        org_id, request, db, user, required_scope="templates:write"
    )

    template = await _tenant_service.get_template(db, tenant.id, template_name)
    if not template:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Template not found",
        )

    await _tenant_service.toggle_template(db, template)
    await db.commit()
    await db.refresh(template)

    logger.info(
        "ACTION: me_template_toggle, user_id=%s, tenant_id=%s, template=%s, is_active=%s",
        user.id,
        tenant.id,
        template_name,
        template.is_active,
    )

    return TemplateResponse.model_validate(template)


@router.delete("/{template_name:path}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_template(
    org_id: uuid.UUID,
    template_name: str,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user_bearer)],
) -> Response:
    """Delete a custom template override for an organisation.

    Permanently removes the stored Jinja2/MJML override identified by
    `template_name`. After deletion the organisation reverts to the
    server-side default for that template name. Raises 404 if no override
    exists. Returns 204 No Content on success.

    **Required scope:** org membership + `templates:write`

    **Example:**
    ```
    curl -X DELETE \\
      -H "Authorization: Bearer <token>" \\
      https://auth.example.com/api/v1/me/organisations/550e8400-e29b-41d4-a716-446655440000/templates/emails/welcome.mjml
    ```
    """
    _user, tenant, _membership = await require_org_membership(
        org_id, request, db, user, required_scope="templates:write"
    )

    template = await _tenant_service.get_template(db, tenant.id, template_name)
    if not template:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Template not found",
        )

    await _tenant_service.delete_template(db, template)
    await db.commit()

    logger.info(
        "ACTION: me_template_delete, user_id=%s, tenant_id=%s, template=%s",
        user.id,
        tenant.id,
        template_name,
    )

    return Response(status_code=status.HTTP_204_NO_CONTENT)
