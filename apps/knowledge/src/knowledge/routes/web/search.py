# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Search web routes."""

import json
import logging
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, Form, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from knowledge.auth.dependencies import get_web_auth_context
from knowledge.auth.models import WebAuthContext
from knowledge.config import TEMPLATES_DIR
from knowledge.database import get_db
from knowledge.models import Collection, Tenant, TenantMember
from knowledge.schemas.search import SearchRequest
from knowledge.services.search import SearchService

logger = logging.getLogger(__name__)

router = APIRouter(tags=["web-search"])
templates = Jinja2Templates(directory=TEMPLATES_DIR)


async def _get_common_context(
    request: Request,
    db: AsyncSession,
    auth_result: WebAuthContext,
) -> dict:
    """Get common template context."""
    user = auth_result.user
    tenant = auth_result.tenant

    # Get user's tenants for switcher
    result = await db.execute(
        select(Tenant)
        .join(TenantMember, Tenant.id == TenantMember.organization_id)
        .where(TenantMember.user_id == user.id, Tenant.is_active == True)  # noqa: E712
    )
    tenants = result.scalars().all()

    return {
        "user": user,
        "tenant": tenant,
        "tenant_member": auth_result.tenant_member,
        "tenants": tenants,
        "active_section": "search",
    }


@router.get("", response_class=HTMLResponse)
async def search_page(
    request: Request,
    q: str = Query("", description="Search query"),
    collection_id: str = Query("", description="Filter by collection"),
    collection_ids: str = Query("", description="Comma-separated collection IDs/slugs"),
    all_collections: bool = Query(False, description="Search across all collections"),
    top_k: int = Query(20, description="Max number of results"),
    threshold: float = Query(0.5, description="Similarity threshold"),
    distance_type: str = Query("cosine", description="Distance metric: cosine, l2, inner_product"),
    include_content: bool = Query(True, description="Include content in results"),
    filters_json: str = Query("", description="Optional JSON filters"),
    db: AsyncSession = Depends(get_db),
    auth_result: WebAuthContext | RedirectResponse = Depends(get_web_auth_context),
):
    """Search interface page."""
    if isinstance(auth_result, RedirectResponse):
        return auth_result

    if not auth_result.tenant:
        return templates.TemplateResponse(
            request,
            "pages/search.html",
            {
                **(await _get_common_context(request, db, auth_result)),
                "collections": [],
                "results": [],
                "query": "",
                "selected_collection": "",
                "info": "No tenant selected",
            },
        )

    tenant = auth_result.tenant

    # Get collections for filter dropdown
    result = await db.execute(
        select(Collection).where(Collection.organization_id == tenant.id).order_by(Collection.name)
    )
    collections = result.scalars().all()

    results = []
    error = None

    # Validate numeric controls
    if top_k < 1 or top_k > 100:
        top_k = 20
    if threshold < 0 or threshold > 1:
        threshold = 0.5

    # Validate distance_type
    valid_distance_types = ["cosine", "l2", "inner_product"]
    if distance_type not in valid_distance_types:
        distance_type = "cosine"

    # Parse optional filters JSON
    filters: dict | None = None
    if filters_json.strip():
        try:
            parsed = json.loads(filters_json)
            if isinstance(parsed, dict):
                filters = parsed
            else:
                error = "Filters must be a JSON object."
        except Exception:
            error = "Filters must be valid JSON."

    # Build collection filters from query params
    collection_ids_list: list[str] = []
    if collection_ids.strip():
        collection_ids_list.extend(
            [item.strip() for item in collection_ids.split(",") if item.strip()]
        )
    if collection_id and collection_id not in collection_ids_list:
        collection_ids_list.append(collection_id)
    selected_collection_values = collection_ids_list
    search_collection_ids = None if all_collections else (collection_ids_list or None)

    if q:
        # Perform semantic search using SearchService
        try:
            search_service = SearchService(db)

            search_request = SearchRequest(
                query=q,
                collection_ids=search_collection_ids,
                top_k=top_k,
                threshold=threshold,
                distance_type=distance_type,  # type: ignore[arg-type]
                filters=filters,
                include_content=include_content,
            )

            response = await search_service.search(tenant.id, search_request)
            results = response.results
        except Exception as e:
            logger.exception("Search failed")
            error = f"Search failed: {str(e)[:200]}"

    return templates.TemplateResponse(
        request,
        "pages/search.html",
        {
            **(await _get_common_context(request, db, auth_result)),
            "collections": collections,
            "results": results,
            "query": q,
            "selected_collection": collection_id,  # backward compatibility
            "selected_collection_ids": collection_ids,  # backward compatibility
            "selected_collection_values": selected_collection_values,
            "selected_all_collections": all_collections,
            "selected_top_k": top_k,
            "selected_threshold": threshold,
            "selected_distance_type": distance_type
            if distance_type in ["cosine", "l2", "inner_product"]
            else "cosine",
            "selected_include_content": include_content,
            "selected_filters_json": filters_json,
            "error": error,
        },
    )


@router.post("", response_class=HTMLResponse)
async def search_submit(
    request: Request,
    query: str = Form(""),
    collection_ids_list: list[str] = Form(default=[]),
    all_collections: str = Form("false"),
    collection_id: str = Form(""),
    collection_ids: str = Form(""),
    top_k: int = Form(20),
    threshold: float = Form(0.5),
    distance_type: str = Form("cosine"),
    include_content: str = Form("true"),
    filters_json: str = Form(""),
    db: AsyncSession = Depends(get_db),
    auth_result: WebAuthContext | RedirectResponse = Depends(get_web_auth_context),
):
    """Handle search form submission - redirect to GET with query params."""
    if isinstance(auth_result, RedirectResponse):
        return auth_result

    params: dict[str, str] = {"q": query}
    all_collections_bool = all_collections.lower() in {"true", "1", "on", "yes"}
    merged_collection_ids: list[str] = []
    merged_collection_ids.extend([item.strip() for item in collection_ids_list if item.strip()])
    if collection_ids.strip():
        merged_collection_ids.extend(
            [item.strip() for item in collection_ids.split(",") if item.strip()]
        )
    if collection_id and collection_id not in merged_collection_ids:
        merged_collection_ids.append(collection_id)
    # Keep order while removing duplicates
    unique_collection_ids: list[str] = list(dict.fromkeys(merged_collection_ids))

    if all_collections_bool:
        params["all_collections"] = "true"
    elif unique_collection_ids:
        params["collection_ids"] = ",".join(unique_collection_ids)
    if top_k != 20:
        params["top_k"] = str(top_k)
    if threshold != 0.5:
        params["threshold"] = str(threshold)
    if distance_type and distance_type != "cosine":
        params["distance_type"] = distance_type
    include_content_bool = include_content.lower() in {"true", "1", "on", "yes"}
    if not include_content_bool:
        params["include_content"] = "false"
    if filters_json.strip():
        params["filters_json"] = filters_json.strip()

    url = f"/search?{urlencode(params)}"

    return RedirectResponse(url=url, status_code=302)
