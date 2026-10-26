# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Contact Groups CRUD routes.

Scopes required:
- contacts:read - View contact groups
- contacts:write - Create, update contact groups
- contacts:delete - Delete contact groups
"""

import contextlib
import re
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, Form, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from internal import TEMPLATES_DIR
from internal.auth.dependencies import (
    require_resource_scopes_or_redirect,
    require_scope_or_redirect,
)
from internal.auth.models import User
from internal.logging import get_logger
from internal.services import mailler_client

router = APIRouter(prefix="/contact-groups", tags=["contact-groups"])
templates = Jinja2Templates(directory=TEMPLATES_DIR)
logger = get_logger(__name__)


def parse_datetime_fields(item: dict[str, Any], fields: list[str]) -> dict[str, Any]:
    """Parse ISO datetime strings to datetime objects for template rendering."""
    for field in fields:
        if field in item and item[field] and isinstance(item[field], str):
            with contextlib.suppress(ValueError, AttributeError):
                item[field] = datetime.fromisoformat(item[field].replace("Z", "+00:00"))
    return item


def parse_groups(groups: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Parse datetime fields in group list."""
    datetime_fields = ["created_at", "updated_at"]
    return [parse_datetime_fields(g, datetime_fields) for g in groups]


def parse_contacts(contacts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Parse datetime fields in contact list."""
    datetime_fields = ["created_at", "updated_at"]
    return [parse_datetime_fields(c, datetime_fields) for c in contacts]


# Scope dependencies (reuse contacts scopes)
require_read = require_resource_scopes_or_redirect(
    "contacts", extra_scopes=["vpn:admin", "billing:read"]
)
require_write = require_scope_or_redirect("contacts:write")
require_delete = require_scope_or_redirect("contacts:delete")


def generate_slug(name: str) -> str:
    """Generate a URL-friendly slug from name."""
    slug = name.lower().strip()
    slug = re.sub(r"[^\w\s-]", "", slug)
    slug = re.sub(r"[-\s]+", "-", slug)
    return slug[:100]


@router.get("", response_class=HTMLResponse)
async def contact_groups_list(
    request: Request,
    page: int = Query(1, ge=1),
    search: str | None = Query(None),
    auth_result: User | RedirectResponse = Depends(require_read),
):
    """List all contact groups with pagination."""
    if not isinstance(auth_result, User):
        return auth_result

    user = auth_result

    logger.info(
        "Contact groups list accessed | user_id=%s page=%d search=%s",
        user.id,
        page,
        search,
    )

    limit = 20

    # Get groups from mailler API
    result = await mailler_client.get_contact_groups(
        page=page,
        page_size=limit,
        search=search,
    )

    # Parse datetime strings for template rendering
    groups = parse_groups(result.get("items", []))
    total = result.get("total", 0)
    total_pages = result.get("pages", 1)

    return templates.TemplateResponse(
        request=request,
        name="admin/contact_groups/list.html",
        context={
            "request": request,
            "active_section": "contact_groups",
            "user": user,
            "groups": groups,
            "total": total,
            "page": page,
            "total_pages": total_pages,
            "search": search,
            "success": request.query_params.get("success"),
            "error": request.query_params.get("error"),
        },
    )


@router.get("/new", response_class=HTMLResponse)
async def contact_group_new(
    request: Request,
    auth_result: User | RedirectResponse = Depends(require_write),
):
    """Show form to create a new contact group."""
    if not isinstance(auth_result, User):
        return auth_result

    user = auth_result

    return templates.TemplateResponse(
        request=request,
        name="admin/contact_groups/form.html",
        context={
            "request": request,
            "active_section": "contact_groups",
            "user": user,
            "group": None,
            "is_edit": False,
            "error": request.query_params.get("error"),
        },
    )


@router.post("/new")
async def contact_group_create(
    request: Request,
    name: str = Form(...),
    slug: str = Form(""),
    description: str = Form(""),
    auth_result: User | RedirectResponse = Depends(require_write),
):
    """Create a new contact group."""
    if not isinstance(auth_result, User):
        return auth_result

    name = name.strip()
    slug = slug.strip() or generate_slug(name)
    desc_val = description.strip() or None

    # Create group via mailler API
    result = await mailler_client.create_contact_group(
        {
            "slug": slug,
            "name": name,
            "description": desc_val,
        }
    )

    if not result:
        return RedirectResponse(
            url="/contact-groups/new?error=Failed+to+create+group",
            status_code=303,
        )

    logger.info(
        "Contact group created | user_id=%s group_id=%s slug=%s",
        auth_result.id,
        result.get("id"),
        slug,
    )

    return RedirectResponse(
        url="/contact-groups?success=Group+created+successfully",
        status_code=303,
    )


@router.get("/{group_id}", response_class=HTMLResponse)
async def contact_group_detail(
    request: Request,
    group_id: int,
    page: int = Query(1, ge=1),
    search: str | None = Query(None),
    auth_result: User | RedirectResponse = Depends(require_read),
):
    """View contact group detail with member list."""
    if not isinstance(auth_result, User):
        return auth_result

    user = auth_result

    group = await mailler_client.get_contact_group(group_id)

    if not group:
        return RedirectResponse(
            url="/contact-groups?error=Group+not+found",
            status_code=303,
        )

    # Get group members from mailler API
    limit = 50
    members_result = await mailler_client.get_group_contacts(
        group_id=group_id,
        page=page,
        page_size=limit,
        search=search,
    )

    # Parse datetime strings for template rendering
    group = parse_datetime_fields(group, ["created_at", "updated_at"])
    members = parse_contacts(members_result.get("items", []))
    total_members = members_result.get("total", 0)
    total_pages = members_result.get("pages", 1)

    return templates.TemplateResponse(
        request=request,
        name="admin/contact_groups/detail.html",
        context={
            "request": request,
            "active_section": "contact_groups",
            "user": user,
            "group": group,
            "members": members,
            "total_members": total_members,
            "page": page,
            "total_pages": total_pages,
            "search": search,
            "success": request.query_params.get("success"),
            "error": request.query_params.get("error"),
        },
    )


@router.get("/{group_id}/edit", response_class=HTMLResponse)
async def contact_group_edit(
    request: Request,
    group_id: int,
    auth_result: User | RedirectResponse = Depends(require_write),
):
    """Show form to edit a contact group."""
    if not isinstance(auth_result, User):
        return auth_result

    user = auth_result

    group = await mailler_client.get_contact_group(group_id)

    if not group:
        return RedirectResponse(
            url="/contact-groups?error=Group+not+found",
            status_code=303,
        )

    # Parse datetime strings for template rendering
    group = parse_datetime_fields(group, ["created_at", "updated_at"])

    return templates.TemplateResponse(
        request=request,
        name="admin/contact_groups/form.html",
        context={
            "request": request,
            "active_section": "contact_groups",
            "user": user,
            "group": group,
            "is_edit": True,
            "error": request.query_params.get("error"),
        },
    )


@router.post("/{group_id}/edit")
async def contact_group_update(
    request: Request,
    group_id: int,
    name: str = Form(...),
    slug: str = Form(""),
    description: str = Form(""),
    auth_result: User | RedirectResponse = Depends(require_write),
):
    """Update a contact group."""
    if not isinstance(auth_result, User):
        return auth_result

    group = await mailler_client.get_contact_group(group_id)

    if not group:
        return RedirectResponse(
            url="/contact-groups?error=Group+not+found",
            status_code=303,
        )

    name = name.strip()
    slug = slug.strip() or generate_slug(name)
    desc_val = description.strip() or None

    # Update group via mailler API
    result = await mailler_client.update_contact_group(
        group_id,
        {
            "name": name,
            "slug": slug,
            "description": desc_val,
        },
    )

    if not result:
        return RedirectResponse(
            url=f"/contact-groups/{group_id}/edit?error=Failed+to+update+group",
            status_code=303,
        )

    logger.info(
        "Contact group updated | user_id=%s group_id=%s",
        auth_result.id,
        group_id,
    )

    return RedirectResponse(
        url=f"/contact-groups/{group_id}?success=Group+updated+successfully",
        status_code=303,
    )


@router.get("/{group_id}/add-contacts", response_class=HTMLResponse)
async def contact_group_add_contacts_form(
    request: Request,
    group_id: int,
    page: int = Query(1, ge=1),
    search: str | None = Query(None),
    auth_result: User | RedirectResponse = Depends(require_write),
):
    """Show form to add contacts to a group."""
    if not isinstance(auth_result, User):
        return auth_result

    user = auth_result

    group = await mailler_client.get_contact_group(group_id)

    if not group:
        return RedirectResponse(
            url="/contact-groups?error=Group+not+found",
            status_code=303,
        )

    # Get contacts NOT in this group via mailler API
    limit = 50
    contacts_result = await mailler_client.get_contacts_not_in_group(
        group_id=group_id,
        page=page,
        page_size=limit,
        search=search,
    )

    # Parse datetime strings for template rendering
    group = parse_datetime_fields(group, ["created_at", "updated_at"])
    contacts = parse_contacts(contacts_result.get("items", []))
    total = contacts_result.get("total", 0)
    total_pages = contacts_result.get("pages", 1)

    return templates.TemplateResponse(
        request=request,
        name="admin/contact_groups/add_contacts.html",
        context={
            "request": request,
            "active_section": "contact_groups",
            "user": user,
            "group": group,
            "contacts": contacts,
            "total": total,
            "page": page,
            "total_pages": total_pages,
            "search": search,
            "error": request.query_params.get("error"),
        },
    )


@router.post("/{group_id}/add-contacts")
async def contact_group_add_contacts(
    request: Request,
    group_id: int,
    auth_result: User | RedirectResponse = Depends(require_write),
):
    """Add contacts to a group."""
    if not isinstance(auth_result, User):
        return auth_result

    form = await request.form()
    # Handle comma-separated IDs from JavaScript (joined with ',')
    contact_ids_raw = str(form.get("contact_ids", ""))
    contact_ids = [id.strip() for id in contact_ids_raw.split(",") if id.strip()]

    if not contact_ids:
        return RedirectResponse(
            url=f"/contact-groups/{group_id}/add-contacts?error=No+contacts+selected",
            status_code=303,
        )

    # Add contacts via mailler API
    result = await mailler_client.add_contacts_to_group(group_id, contact_ids)

    added = result.get("added", 0) if result else 0

    logger.info(
        "Contacts added to group | user_id=%s group_id=%d added=%d",
        auth_result.id,
        group_id,
        added,
    )

    return RedirectResponse(
        url=f"/contact-groups/{group_id}?success={added}+contact(s)+added",
        status_code=303,
    )


@router.post("/{group_id}/remove-contacts")
async def contact_group_remove_contacts(
    request: Request,
    group_id: int,
    auth_result: User | RedirectResponse = Depends(require_write),
):
    """Remove contacts from a group."""
    if not isinstance(auth_result, User):
        return auth_result

    form = await request.form()
    # Handle comma-separated IDs from JavaScript (joined with ',')
    contact_ids_raw = str(form.get("contact_ids", ""))
    contact_ids = [id.strip() for id in contact_ids_raw.split(",") if id.strip()]

    if not contact_ids:
        return RedirectResponse(
            url=f"/contact-groups/{group_id}?error=No+contacts+selected",
            status_code=303,
        )

    # Remove contacts via mailler API
    result = await mailler_client.remove_contacts_from_group(group_id, contact_ids)

    removed = result.get("removed", 0) if result else 0

    logger.info(
        "Contacts removed from group | user_id=%s group_id=%d removed=%d",
        auth_result.id,
        group_id,
        removed,
    )

    return RedirectResponse(
        url=f"/contact-groups/{group_id}?success={removed}+contact(s)+removed",
        status_code=303,
    )


@router.post("/bulk-delete")
async def contact_group_bulk_delete(
    request: Request,
    auth_result: User | RedirectResponse = Depends(require_delete),
):
    """Delete multiple contact groups."""
    if not isinstance(auth_result, User):
        return auth_result

    form = await request.form()
    group_ids_raw = form.getlist("group_ids")

    if not group_ids_raw:
        return RedirectResponse(
            url="/contact-groups?error=No+groups+selected",
            status_code=303,
        )

    try:
        group_ids = [int(str(id_str)) for id_str in group_ids_raw if id_str]
    except ValueError:
        return RedirectResponse(
            url="/contact-groups?error=Invalid+group+IDs",
            status_code=303,
        )

    # Delete groups via mailler API
    deleted_count = 0
    for group_id in group_ids:
        if await mailler_client.delete_contact_group(group_id):
            deleted_count += 1

    logger.info(
        "Contact groups bulk deleted | user_id=%s deleted_count=%d",
        auth_result.id,
        deleted_count,
    )

    return RedirectResponse(
        url=f"/contact-groups?success={deleted_count}+group(s)+deleted+successfully",
        status_code=303,
    )


@router.post("/{group_id}/delete")
async def contact_group_delete(
    request: Request,
    group_id: int,
    auth_result: User | RedirectResponse = Depends(require_delete),
):
    """Delete a contact group."""
    if not isinstance(auth_result, User):
        return auth_result

    group = await mailler_client.get_contact_group(group_id)

    if not group:
        return RedirectResponse(
            url="/contact-groups?error=Group+not+found",
            status_code=303,
        )

    result = await mailler_client.delete_contact_group(group_id)

    if not result:
        return RedirectResponse(
            url="/contact-groups?error=Failed+to+delete+group",
            status_code=303,
        )

    logger.info(
        "Contact group deleted | user_id=%s group_id=%s",
        auth_result.id,
        group_id,
    )

    return RedirectResponse(
        url="/contact-groups?success=Group+deleted+successfully",
        status_code=303,
    )
