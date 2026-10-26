# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Contacts CRUD routes with CSV import/export.

Uses Mailler API for all contact operations.

Scopes required:
- contacts:read - View contacts
- contacts:write - Create, update contacts, import CSV
- contacts:delete - Delete contacts
"""

import contextlib
import csv
import io
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, File, Form, Query, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse, StreamingResponse
from fastapi.templating import Jinja2Templates

from internal import TEMPLATES_DIR
from internal.auth.dependencies import (
    require_resource_scopes_or_redirect,
    require_scope_or_redirect,
)
from internal.auth.models import User
from internal.logging import get_logger
from internal.services.mailler_client import mailler_client

router = APIRouter(prefix="/contacts", tags=["contacts"])
templates = Jinja2Templates(directory=TEMPLATES_DIR)
logger = get_logger(__name__)


def parse_datetime_fields(item: dict[str, Any], fields: list[str]) -> dict[str, Any]:
    """Parse ISO datetime strings to datetime objects for template rendering."""
    for field in fields:
        if field in item and item[field] and isinstance(item[field], str):
            with contextlib.suppress(ValueError, AttributeError):
                item[field] = datetime.fromisoformat(item[field].replace("Z", "+00:00"))
    return item


def parse_contacts(contacts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Parse datetime fields in contact list."""
    datetime_fields = ["created_at", "updated_at"]
    return [parse_datetime_fields(c, datetime_fields) for c in contacts]


def parse_groups(groups: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Parse datetime fields in group list."""
    datetime_fields = ["created_at", "updated_at"]
    return [parse_datetime_fields(g, datetime_fields) for g in groups]


# Scope dependencies
require_read = require_resource_scopes_or_redirect(
    "contacts", extra_scopes=["vpn:admin", "billing:read"]
)
require_write = require_scope_or_redirect("contacts:write")
require_delete = require_scope_or_redirect("contacts:delete")

# Contact statuses
CONTACT_STATUSES = ["active", "unsubscribed", "bounced", "complained"]


@router.get("", response_class=HTMLResponse)
async def contacts_list(
    request: Request,
    page: int = Query(1, ge=1),
    search: str | None = Query(None),
    status: str | None = Query(None),
    group: str | None = Query(None),
    auth_result: User | RedirectResponse = Depends(require_read),
):
    """List all contacts with pagination, search, and filtering."""
    if not isinstance(auth_result, User):
        return auth_result

    user = auth_result

    # Convert group to int if it is a number (anything else is no filter)
    group_id = int(group) if group and group.strip().isdigit() else None

    logger.info(
        "Contacts list accessed | user_id=%s page=%d search=%s status=%s group=%s",
        user.id,
        page,
        search,
        status,
        group_id,
    )

    # Fetch contacts from Mailler API
    data = await mailler_client.get_contacts(
        page=page,
        page_size=50,
        status=status if status in CONTACT_STATUSES else None,
        search=search,
        group_id=group_id,
    )

    # Fetch groups for filter dropdown
    groups_data = await mailler_client.get_contact_groups(page=1, page_size=100)

    # Parse datetime strings for template rendering
    contacts = parse_contacts(data.get("items", []))
    groups = parse_groups(groups_data.get("items", []))

    return templates.TemplateResponse(
        request=request,
        name="admin/contacts/list.html",
        context={
            "request": request,
            "active_section": "contacts",
            "user": user,
            "contacts": contacts,
            "groups": groups,
            "total": data.get("total", 0),
            "page": page,
            "total_pages": data.get("pages", 1),
            "search": search,
            "status_filter": status,
            "group_filter": group,
            "statuses": CONTACT_STATUSES,
            "success": request.query_params.get("success"),
            "error": request.query_params.get("error"),
        },
    )


@router.get("/new", response_class=HTMLResponse)
async def contact_new(
    request: Request,
    auth_result: User | RedirectResponse = Depends(require_write),
):
    """Show form to create a new contact."""
    if not isinstance(auth_result, User):
        return auth_result

    user = auth_result

    # Get all groups for selection
    groups_data = await mailler_client.get_contact_groups(page=1, page_size=100)

    # Parse datetime fields for template rendering
    groups = parse_groups(groups_data.get("items", []))

    return templates.TemplateResponse(
        request=request,
        name="admin/contacts/form.html",
        context={
            "request": request,
            "active_section": "contacts",
            "user": user,
            "contact": None,
            "is_edit": False,
            "groups": groups,
            "current_group_ids": [],
            "statuses": CONTACT_STATUSES,
            "error": request.query_params.get("error"),
        },
    )


@router.post("/new")
async def contact_create(
    request: Request,
    email: str = Form(...),
    first_name: str = Form(""),
    last_name: str = Form(""),
    status: str = Form("active"),
    source: str = Form(""),
    group_ids: list[int] = Form(default=[]),
    auth_result: User | RedirectResponse = Depends(require_write),
):
    """Create a new contact."""
    if not isinstance(auth_result, User):
        return auth_result

    email = email.lower().strip()
    first_name_val = first_name.strip() or None
    last_name_val = last_name.strip() or None
    source_val = source.strip() or None

    if status not in CONTACT_STATUSES:
        status = "active"

    # Create contact via Mailler API
    result = await mailler_client.create_contact(
        {
            "email": email,
            "first_name": first_name_val,
            "last_name": last_name_val,
            "source": source_val,
        }
    )

    if not result:
        return RedirectResponse(
            url="/contacts/new?error=Failed+to+create+contact",
            status_code=303,
        )

    contact_id = result.get("id")

    # Add to groups if specified
    if group_ids and contact_id:
        for group_id in group_ids:
            await mailler_client.add_contacts_to_group(group_id, [str(contact_id)])

    logger.info(
        "Contact created | user_id=%s contact_id=%s email=%s",
        auth_result.id,
        contact_id,
        email,
    )

    return RedirectResponse(
        url="/contacts?success=Contact+created+successfully",
        status_code=303,
    )


@router.get("/import", response_class=HTMLResponse)
async def contact_import_form(
    request: Request,
    auth_result: User | RedirectResponse = Depends(require_write),
):
    """Show CSV import form."""
    if not isinstance(auth_result, User):
        return auth_result

    user = auth_result

    return templates.TemplateResponse(
        request=request,
        name="admin/contacts/import.html",
        context={
            "request": request,
            "active_section": "contacts",
            "user": user,
            "error": request.query_params.get("error"),
        },
    )


@router.post("/import")
async def contact_import(
    request: Request,
    file: UploadFile = File(...),
    update_existing: bool = Form(False),
    source: str = Form("csv_import"),
    auth_result: User | RedirectResponse = Depends(require_write),
):
    """Import contacts from CSV file."""
    if not isinstance(auth_result, User):
        return auth_result

    # Validate file type
    if not file.filename or not file.filename.endswith(".csv"):
        return RedirectResponse(
            url="/contacts/import?error=Please+upload+a+CSV+file",
            status_code=303,
        )

    try:
        content = await file.read()
        text = content.decode("utf-8-sig")
        reader = csv.DictReader(io.StringIO(text))

        # Map CSV columns to contact fields
        contacts = []
        for row in reader:
            email = row.get("email", "").strip().lower()
            if not email:
                continue

            contacts.append(
                {
                    "email": email,
                    "first_name": row.get("first_name", "").strip() or None,
                    "last_name": row.get("last_name", "").strip() or None,
                    "source": source.strip() or "csv_import",
                }
            )

        if not contacts:
            return RedirectResponse(
                url="/contacts/import?error=No+valid+contacts+found+in+CSV",
                status_code=303,
            )

        # Bulk create via Mailler API
        result = await mailler_client.create_contacts_bulk(
            contacts=contacts,
            skip_existing=not update_existing,
        )

        logger.info(
            "CSV import by user | user_id=%s created=%d skipped=%d failed=%d",
            auth_result.id,
            result.get("created", 0),
            result.get("skipped", 0),
            result.get("failed", 0),
        )

        msg = f"Imported+{result.get('created', 0)}+contacts"
        if result.get("skipped"):
            msg += f",+skipped+{result['skipped']}"
        if result.get("failed"):
            msg += f",+failed+{result['failed']}"

        return RedirectResponse(
            url=f"/contacts?success={msg}",
            status_code=303,
        )

    except Exception as e:
        logger.error("CSV import failed: %s", e)
        return RedirectResponse(
            url=f"/contacts/import?error=Import+failed:+{str(e)[:50]}",
            status_code=303,
        )


@router.get("/export")
async def contact_export(
    request: Request,
    group: str | None = Query(None),
    auth_result: User | RedirectResponse = Depends(require_read),
):
    """Export contacts to CSV file."""
    if not isinstance(auth_result, User):
        return auth_result

    # Convert group to int if it is a number (anything else is no filter)
    group_id = int(group) if group and group.strip().isdigit() else None

    # Fetch all contacts (paginated, up to reasonable limit)
    all_contacts = []
    page = 1
    while True:
        data = await mailler_client.get_contacts(
            page=page,
            page_size=100,
            group_id=group_id,
        )
        items = data.get("items", [])
        all_contacts.extend(items)
        if page >= data.get("pages", 1):
            break
        page += 1

    # Generate CSV
    output = io.StringIO()
    writer = csv.DictWriter(
        output, fieldnames=["email", "first_name", "last_name", "status", "source"]
    )
    writer.writeheader()
    for contact in all_contacts:
        writer.writerow(
            {
                "email": contact.get("email", ""),
                "first_name": contact.get("first_name", ""),
                "last_name": contact.get("last_name", ""),
                "status": contact.get("status", ""),
                "source": contact.get("source", ""),
            }
        )

    csv_content = output.getvalue()

    filename = "contacts"
    if group_id:
        group_data = await mailler_client.get_contact_group(group_id)
        if group_data:
            filename = f"contacts_{group_data.get('slug', group_id)}"

    logger.info(
        "CSV export by user | user_id=%s group=%s count=%d",
        auth_result.id,
        group_id,
        len(all_contacts),
    )

    return StreamingResponse(
        iter([csv_content]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}.csv"},
    )


@router.get("/{contact_id}", response_class=HTMLResponse)
async def contact_detail(
    request: Request,
    contact_id: str,
    auth_result: User | RedirectResponse = Depends(require_read),
):
    """View contact detail."""
    if not isinstance(auth_result, User):
        return auth_result

    user = auth_result

    # Fetch contact from Mailler API
    contact = await mailler_client.get_contact(contact_id)

    if not contact:
        return RedirectResponse(
            url="/contacts?error=Contact+not+found",
            status_code=303,
        )

    # Parse datetime fields for template rendering
    contact = parse_datetime_fields(contact, ["created_at", "updated_at"])

    return templates.TemplateResponse(
        request=request,
        name="admin/contacts/detail.html",
        context={
            "request": request,
            "active_section": "contacts",
            "user": user,
            "contact": contact,
            "success": request.query_params.get("success"),
            "error": request.query_params.get("error"),
        },
    )


@router.get("/{contact_id}/edit", response_class=HTMLResponse)
async def contact_edit(
    request: Request,
    contact_id: str,
    auth_result: User | RedirectResponse = Depends(require_write),
):
    """Show form to edit a contact."""
    if not isinstance(auth_result, User):
        return auth_result

    user = auth_result

    # Fetch contact from Mailler API
    contact = await mailler_client.get_contact(contact_id)

    if not contact:
        return RedirectResponse(
            url="/contacts?error=Contact+not+found",
            status_code=303,
        )

    # Get all groups for selection
    groups_data = await mailler_client.get_contact_groups(page=1, page_size=100)

    # Get current group IDs from contact.groups
    current_group_ids = [g.get("id") for g in contact.get("groups", []) if g.get("id")]

    # Parse datetime fields for template rendering
    contact = parse_datetime_fields(contact, ["created_at", "updated_at"])
    groups = parse_groups(groups_data.get("items", []))

    return templates.TemplateResponse(
        request=request,
        name="admin/contacts/form.html",
        context={
            "request": request,
            "active_section": "contacts",
            "user": user,
            "contact": contact,
            "is_edit": True,
            "groups": groups,
            "current_group_ids": current_group_ids,
            "statuses": CONTACT_STATUSES,
            "error": request.query_params.get("error"),
        },
    )


@router.post("/{contact_id}/edit")
async def contact_update(
    request: Request,
    contact_id: str,
    first_name: str = Form(""),
    last_name: str = Form(""),
    status: str = Form("active"),
    source: str = Form(""),
    group_ids: list[int] = Form(default=[]),
    auth_result: User | RedirectResponse = Depends(require_write),
):
    """Update a contact."""
    if not isinstance(auth_result, User):
        return auth_result

    first_name_val = first_name.strip() or None
    last_name_val = last_name.strip() or None
    source_val = source.strip() or None

    if status not in CONTACT_STATUSES:
        status = "active"

    # Get current contact to compare groups
    current_contact = await mailler_client.get_contact(contact_id)
    if not current_contact:
        return RedirectResponse(
            url="/contacts?error=Contact+not+found",
            status_code=303,
        )

    # Update contact via Mailler API
    result = await mailler_client.update_contact(
        contact_id,
        {
            "first_name": first_name_val,
            "last_name": last_name_val,
            "status": status,
            "source": source_val,
        },
    )

    if not result:
        return RedirectResponse(
            url=f"/contacts/{contact_id}/edit?error=Failed+to+update+contact",
            status_code=303,
        )

    # Update group memberships
    current_group_ids = {g.get("id") for g in current_contact.get("groups", []) if g.get("id")}
    new_group_ids = set(group_ids)

    # Remove from groups no longer selected
    for gid in current_group_ids - new_group_ids:
        await mailler_client.remove_contacts_from_group(gid, [contact_id])

    # Add to new groups
    for gid in new_group_ids - current_group_ids:
        await mailler_client.add_contacts_to_group(gid, [contact_id])

    logger.info(
        "Contact updated | user_id=%s contact_id=%s",
        auth_result.id,
        contact_id,
    )

    return RedirectResponse(
        url=f"/contacts/{contact_id}?success=Contact+updated+successfully",
        status_code=303,
    )


@router.post("/{contact_id}/unsubscribe")
async def contact_unsubscribe(
    request: Request,
    contact_id: str,
    auth_result: User | RedirectResponse = Depends(require_write),
):
    """Mark a contact as unsubscribed."""
    if not isinstance(auth_result, User):
        return auth_result

    result = await mailler_client.unsubscribe_contact(contact_id)

    if not result:
        return RedirectResponse(
            url="/contacts?error=Contact+not+found",
            status_code=303,
        )

    logger.info(
        "Contact unsubscribed | user_id=%s contact_id=%s",
        auth_result.id,
        contact_id,
    )

    return RedirectResponse(
        url=f"/contacts/{contact_id}?success=Contact+marked+as+unsubscribed",
        status_code=303,
    )


@router.post("/{contact_id}/delete")
async def contact_delete(
    request: Request,
    contact_id: str,
    auth_result: User | RedirectResponse = Depends(require_delete),
):
    """Delete a contact."""
    if not isinstance(auth_result, User):
        return auth_result

    success = await mailler_client.delete_contact(contact_id)

    if not success:
        return RedirectResponse(
            url="/contacts?error=Failed+to+delete+contact",
            status_code=303,
        )

    logger.info(
        "Contact deleted | user_id=%s contact_id=%s",
        auth_result.id,
        contact_id,
    )

    return RedirectResponse(
        url="/contacts?success=Contact+deleted+successfully",
        status_code=303,
    )


@router.post("/bulk-delete")
async def contacts_bulk_delete(
    request: Request,
    auth_result: User | RedirectResponse = Depends(require_delete),
):
    """Delete multiple contacts."""
    if not isinstance(auth_result, User):
        return auth_result

    form = await request.form()
    # Handle comma-separated IDs from JavaScript (joined with ',')
    contact_ids_raw = str(form.get("contact_ids", ""))
    contact_ids = [id.strip() for id in contact_ids_raw.split(",") if id.strip()]

    if not contact_ids:
        return RedirectResponse(
            url="/contacts?error=No+contacts+selected",
            status_code=303,
        )

    deleted = 0
    for contact_id in contact_ids:
        if await mailler_client.delete_contact(contact_id):
            deleted += 1

    logger.info(
        "Bulk delete by user | user_id=%s deleted=%d",
        auth_result.id,
        deleted,
    )

    return RedirectResponse(
        url=f"/contacts?success={deleted}+contact(s)+deleted",
        status_code=303,
    )


@router.post("/bulk-add-to-group")
async def contacts_bulk_add_to_group(
    request: Request,
    auth_result: User | RedirectResponse = Depends(require_write),
):
    """Add multiple contacts to a group."""
    if not isinstance(auth_result, User):
        return auth_result

    form = await request.form()
    # Handle comma-separated IDs from JavaScript (joined with ',')
    contact_ids_raw = str(form.get("contact_ids", ""))
    contact_ids = [id.strip() for id in contact_ids_raw.split(",") if id.strip()]
    group_id_raw = str(form.get("group_id", ""))

    if not contact_ids or not group_id_raw:
        return RedirectResponse(
            url="/contacts?error=Missing+contacts+or+group",
            status_code=303,
        )

    try:
        group_id_int = int(group_id_raw)
    except ValueError:
        return RedirectResponse(
            url="/contacts?error=Invalid+IDs",
            status_code=303,
        )

    result = await mailler_client.add_contacts_to_group(group_id_int, contact_ids)

    logger.info(
        "Bulk add to group by user | user_id=%s group_id=%d added=%d",
        auth_result.id,
        group_id_int,
        result.get("added", 0),
    )

    return RedirectResponse(
        url=f"/contacts?success={result.get('added', 0)}+contact(s)+added+to+group",
        status_code=303,
    )
