# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Templates a client can choose for its domains."""

from fastapi import APIRouter, Depends
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from custom_domain.auth import AuthContext
from custom_domain.database import get_db
from custom_domain.models import NginxTemplate
from custom_domain.routes.access import require_client_scopes
from custom_domain.schemas import AvailableTemplate, AvailableTemplateListResponse

router = APIRouter(prefix="/templates", tags=["templates"])


@router.get("", response_model=AvailableTemplateListResponse)
async def list_available_templates(
    db: AsyncSession = Depends(get_db),
    auth: AuthContext = Depends(require_client_scopes("custom-domain:read")),
):
    """List the active templates the caller may put on its domains.

    These are the shared templates and the ones owned by the caller's client; the
    template sources are not returned (only administrators read them). Use an
    ``id`` as ``nginx_template_id`` when registering or updating a domain.
    """
    query = select(NginxTemplate).where(NginxTemplate.is_active.is_(True))
    if not auth.is_admin:
        query = query.where(
            or_(NginxTemplate.client_id.is_(None), NginxTemplate.client_id == auth.user.client_id)
        )
    templates = (await db.execute(query.order_by(NginxTemplate.name))).scalars().all()

    items = [
        AvailableTemplate(
            id=t.id,
            slug=t.slug,
            name=t.name,
            description=t.description,
            shared=t.client_id is None,
        )
        for t in templates
    ]
    return AvailableTemplateListResponse(items=items, total=len(items))
