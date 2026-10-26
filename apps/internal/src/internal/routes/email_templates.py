# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Email Templates CRUD routes with MJML editor.

Uses Mailler API for all template operations.

Scopes required:
- email_templates:read - View email templates
- email_templates:write - Create, update email templates
- email_templates:delete - Delete email templates
"""

import contextlib
import re
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, Form, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from internal import TEMPLATES_DIR
from internal.auth.dependencies import (
    require_resource_scopes_or_redirect,
    require_scope_or_redirect,
)
from internal.auth.models import User
from internal.logging import get_logger
from internal.services.mailler_client import mailler_client

router = APIRouter(prefix="/email-templates", tags=["email-templates"])
templates = Jinja2Templates(directory=TEMPLATES_DIR)
logger = get_logger(__name__)


def parse_datetime_fields(item: dict[str, Any], fields: list[str]) -> dict[str, Any]:
    """Parse ISO datetime strings to datetime objects for template rendering."""
    for field in fields:
        if field in item and item[field] and isinstance(item[field], str):
            with contextlib.suppress(ValueError, AttributeError):
                item[field] = datetime.fromisoformat(item[field].replace("Z", "+00:00"))
    return item


def parse_templates_list(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Parse datetime fields in template list."""
    datetime_fields = ["created_at", "updated_at"]
    return [parse_datetime_fields(t, datetime_fields) for t in items]


# Scope dependencies
require_read = require_resource_scopes_or_redirect(
    "email_templates", extra_scopes=["vpn:admin", "billing:read"]
)
require_write = require_scope_or_redirect("email_templates:write")
require_delete = require_scope_or_redirect("email_templates:delete")

# Template statuses
TEMPLATE_STATUSES = ["draft", "active", "archived"]

# Default MJML for new templates - GOABONGA theme (dark mode with green accent)
DEFAULT_MJML = """<mjml>
  <mj-head>
    <mj-title>%subject%</mj-title>
    <mj-preview>Preview text here</mj-preview>
    <mj-attributes>
      <mj-all font-family="Lato, Arial, Helvetica, sans-serif" />
      <mj-text color="#ffffff" line-height="1.6" />
      <mj-button background-color="#00ff00" color="#000000" font-weight="bold" text-transform="uppercase" />
    </mj-attributes>
  </mj-head>
  <mj-body background-color="#000000">
    <mj-section background-color="#000000" padding="20px 20px 10px">
      <mj-column>
        <mj-text font-size="24px" font-weight="bold" text-transform="uppercase">GOABONGA</mj-text>
      </mj-column>
    </mj-section>
    <mj-section background-color="#000000" padding="20px">
      <mj-column>
        <mj-text font-size="28px" font-weight="bold">Hello %first_name%!</mj-text>
        <mj-text font-size="16px" padding-top="20px">Your email content goes here. You can use variables like %email% to personalize your message.</mj-text>
        <mj-button href="https://example.invalid" padding-top="30px">Call to Action</mj-button>
      </mj-column>
    </mj-section>
    <mj-section background-color="#ffffff" padding="15px 20px">
      <mj-column>
        <mj-text font-size="12px" color="#000000" align="center">GOABONGA - Terre Rouge, 26410 Boulc, France</mj-text>
        <mj-text font-size="11px" color="#666666" align="center" padding-top="5px">
          <a href="%unsubscribe_url%" style="color: #666666;">Unsubscribe</a>
        </mj-text>
      </mj-column>
    </mj-section>
  </mj-body>
</mjml>"""


def generate_slug(name: str) -> str:
    """Generate a URL-friendly slug from name."""
    slug = name.lower().strip()
    slug = re.sub(r"[^\w\s-]", "", slug)
    slug = re.sub(r"[-\s]+", "-", slug)
    return slug[:100]


@router.get("", response_class=HTMLResponse)
async def email_templates_list(
    request: Request,
    page: int = Query(1, ge=1),
    search: str | None = Query(None),
    status: str | None = Query(None),
    auth_result: User | RedirectResponse = Depends(require_read),
):
    """List all email templates with pagination and filtering."""
    if not isinstance(auth_result, User):
        return auth_result

    user = auth_result

    logger.info(
        "Email templates list accessed | user_id=%s page=%d search=%s status=%s",
        user.id,
        page,
        search,
        status,
    )

    # Fetch templates from Mailler API
    data = await mailler_client.get_templates(
        page=page,
        page_size=20,
        status=status if status in TEMPLATE_STATUSES else None,
        search=search,
    )

    # Parse datetime strings for template rendering
    email_templates_items = parse_templates_list(data.get("items", []))

    return templates.TemplateResponse(
        request=request,
        name="admin/email_templates/list.html",
        context={
            "request": request,
            "active_section": "email_templates",
            "user": user,
            "templates": email_templates_items,
            "total": data.get("total", 0),
            "page": page,
            "total_pages": data.get("pages", 1),
            "search": search,
            "status_filter": status,
            "statuses": TEMPLATE_STATUSES,
            "success": request.query_params.get("success"),
            "error": request.query_params.get("error"),
        },
    )


@router.get("/new", response_class=HTMLResponse)
async def email_template_new(
    request: Request,
    auth_result: User | RedirectResponse = Depends(require_write),
):
    """Show form to create a new email template."""
    if not isinstance(auth_result, User):
        return auth_result

    user = auth_result

    logger.info("Email template new form accessed | user_id=%s", user.id)

    return templates.TemplateResponse(
        request=request,
        name="admin/email_templates/form.html",
        context={
            "request": request,
            "active_section": "email_templates",
            "user": user,
            "template": None,
            "is_edit": False,
            "default_mjml": DEFAULT_MJML,
            "statuses": TEMPLATE_STATUSES,
        },
    )


@router.post("/new")
async def email_template_create(
    request: Request,
    name: str = Form(...),
    slug: str = Form(""),
    description: str = Form(""),
    subject_template: str = Form(...),
    mjml_source: str = Form(...),
    plain_text: str = Form(""),
    status: str = Form("draft"),
    auth_result: User | RedirectResponse = Depends(require_write),
):
    """Create a new email template."""
    if not isinstance(auth_result, User):
        return auth_result

    name = name.strip()
    slug = slug.strip() or generate_slug(name)
    description = description.strip()
    subject_template = subject_template.strip()
    mjml_source = mjml_source.strip()
    plain_text = plain_text.strip()

    if status not in TEMPLATE_STATUSES:
        status = "draft"

    # Create template via Mailler API
    result = await mailler_client.create_template(
        {
            "slug": slug,
            "name": name,
            "description": description or None,
            "subject_template": subject_template,
            "mjml_source": mjml_source,
            "plain_text": plain_text or None,
            "status": status,
        }
    )

    if not result:
        return RedirectResponse(
            url="/email-templates/new?error=Failed+to+create+template",
            status_code=303,
        )

    logger.info(
        "Email template created | user_id=%s template_id=%s slug=%s",
        auth_result.id,
        result.get("id"),
        slug,
    )

    return RedirectResponse(
        url="/email-templates?success=Template+created+successfully",
        status_code=303,
    )


@router.get("/{template_id}", response_class=HTMLResponse)
async def email_template_detail(
    request: Request,
    template_id: int,
    auth_result: User | RedirectResponse = Depends(require_read),
):
    """View email template detail with preview."""
    if not isinstance(auth_result, User):
        return auth_result

    user = auth_result

    # Fetch template from Mailler API
    email_template = await mailler_client.get_template(template_id)

    if not email_template:
        return RedirectResponse(
            url="/email-templates?error=Template+not+found",
            status_code=303,
        )

    # Parse datetime fields for template rendering
    email_template = parse_datetime_fields(email_template, ["created_at", "updated_at"])

    logger.info(
        "Email template detail accessed | user_id=%s template_id=%s",
        user.id,
        template_id,
    )

    return templates.TemplateResponse(
        request=request,
        name="admin/email_templates/detail.html",
        context={
            "request": request,
            "active_section": "email_templates",
            "user": user,
            "template": email_template,
            "success": request.query_params.get("success"),
            "error": request.query_params.get("error"),
        },
    )


@router.get("/{template_id}/edit", response_class=HTMLResponse)
async def email_template_edit(
    request: Request,
    template_id: int,
    auth_result: User | RedirectResponse = Depends(require_write),
):
    """Show form to edit an email template."""
    if not isinstance(auth_result, User):
        return auth_result

    user = auth_result

    # Fetch template from Mailler API
    email_template = await mailler_client.get_template(template_id)

    if not email_template:
        return RedirectResponse(
            url="/email-templates?error=Template+not+found",
            status_code=303,
        )

    # Parse datetime fields for template rendering
    email_template = parse_datetime_fields(email_template, ["created_at", "updated_at"])

    logger.info(
        "Email template edit form accessed | user_id=%s template_id=%s",
        user.id,
        template_id,
    )

    return templates.TemplateResponse(
        request=request,
        name="admin/email_templates/form.html",
        context={
            "request": request,
            "active_section": "email_templates",
            "user": user,
            "template": email_template,
            "is_edit": True,
            "default_mjml": DEFAULT_MJML,
            "statuses": TEMPLATE_STATUSES,
        },
    )


@router.post("/{template_id}/edit")
async def email_template_update(
    request: Request,
    template_id: int,
    name: str = Form(...),
    description: str = Form(""),
    subject_template: str = Form(...),
    mjml_source: str = Form(...),
    plain_text: str = Form(""),
    status: str = Form("draft"),
    auth_result: User | RedirectResponse = Depends(require_write),
):
    """Update an email template."""
    if not isinstance(auth_result, User):
        return auth_result

    name = name.strip()
    description = description.strip()
    subject_template = subject_template.strip()
    mjml_source = mjml_source.strip()
    plain_text = plain_text.strip()

    if status not in TEMPLATE_STATUSES:
        status = "draft"

    # Update template via Mailler API
    result = await mailler_client.update_template(
        template_id,
        {
            "name": name,
            "description": description or None,
            "subject_template": subject_template,
            "mjml_source": mjml_source,
            "plain_text": plain_text or None,
            "status": status,
        },
    )

    if not result:
        return RedirectResponse(
            url=f"/email-templates/{template_id}/edit?error=Failed+to+update+template",
            status_code=303,
        )

    logger.info(
        "Email template updated | user_id=%s template_id=%s",
        auth_result.id,
        template_id,
    )

    return RedirectResponse(
        url=f"/email-templates/{template_id}?success=Template+updated+successfully",
        status_code=303,
    )


@router.post("/compile", response_class=JSONResponse)
async def email_template_compile(
    request: Request,
    auth_result: User | RedirectResponse = Depends(require_read),
):
    """AJAX endpoint to compile MJML and return HTML preview."""
    if not isinstance(auth_result, User):
        return JSONResponse({"error": "Unauthorized"}, status_code=401)

    try:
        body = await request.json()
        mjml_source = body.get("mjml_source", "")
        subject = body.get("subject", "")
        sample_data = body.get("sample_data", {})
    except Exception:
        return JSONResponse({"error": "Invalid JSON"}, status_code=400)

    if not mjml_source:
        return JSONResponse({"error": "No MJML source provided"}, status_code=400)

    # Compile via Mailler API
    result = await mailler_client.compile_mjml(mjml_source)

    if result.get("errors"):
        return JSONResponse(
            {
                "success": False,
                "errors": result["errors"],
                "html": "",
            }
        )

    html = result.get("html", "")

    # Extract variables (simple regex for %var% and {{var}})
    import re

    pattern = r"(?:%(\w+)%|\{\{\s*(\w+)\s*\}\})"
    matches = re.findall(pattern, mjml_source + " " + subject)
    variables = list({m[0] or m[1] for m in matches if m[0] or m[1]})

    # Render with sample data if provided
    rendered_subject = subject
    if sample_data:
        from jinja2 import Environment

        env = Environment(autoescape=True)
        try:
            html_tpl = env.from_string(html)
            html = html_tpl.render(sample_data)
            subj_tpl = env.from_string(subject)
            rendered_subject = subj_tpl.render(sample_data)
        except Exception:
            pass

    return JSONResponse(
        {
            "success": True,
            "html": html,
            "subject": rendered_subject,
            "variables": variables,
            "errors": [],
        }
    )


@router.post("/{template_id}/preview", response_class=JSONResponse)
async def email_template_preview(
    request: Request,
    template_id: int,
    auth_result: User | RedirectResponse = Depends(require_read),
):
    """Preview email template with sample data."""
    if not isinstance(auth_result, User):
        return JSONResponse({"error": "Unauthorized"}, status_code=401)

    try:
        body = await request.json()
        sample_data = body.get("sample_data", {})
    except Exception:
        sample_data = {}

    # Default sample data
    default_data = {
        "first_name": "John",
        "last_name": "Doe",
        "email": "john.doe@example.com",
        "subject": "Sample Subject",
    }
    merged_data = {**default_data, **sample_data}

    # Render via Mailler API
    result = await mailler_client.render_template(template_id, merged_data)

    if not result:
        return JSONResponse({"error": "Template not found"}, status_code=404)

    return JSONResponse(
        {
            "success": True,
            "html": result.get("html", ""),
            "subject": result.get("subject", ""),
            "plain_text": result.get("plain_text"),
        }
    )


@router.post("/{template_id}/duplicate")
async def email_template_duplicate(
    request: Request,
    template_id: int,
    auth_result: User | RedirectResponse = Depends(require_write),
):
    """Duplicate an email template."""
    if not isinstance(auth_result, User):
        return auth_result

    # Fetch original template
    email_template = await mailler_client.get_template(template_id)

    if not email_template:
        return RedirectResponse(
            url="/email-templates?error=Template+not+found",
            status_code=303,
        )

    # Create duplicate with new slug
    new_slug = f"{email_template.get('slug', 'template')}-copy"
    result = await mailler_client.create_template(
        {
            "slug": new_slug,
            "name": f"{email_template.get('name', 'Template')} (Copy)",
            "description": email_template.get("description"),
            "subject_template": email_template.get("subject_template", ""),
            "mjml_source": email_template.get("mjml_source", ""),
            "plain_text": email_template.get("plain_text"),
            "status": "draft",
        }
    )

    if not result:
        return RedirectResponse(
            url="/email-templates?error=Failed+to+duplicate+template",
            status_code=303,
        )

    logger.info(
        "Email template duplicated | user_id=%s source_id=%s new_id=%s",
        auth_result.id,
        template_id,
        result.get("id"),
    )

    return RedirectResponse(
        url=f"/email-templates/{result.get('id')}/edit?success=Template+duplicated",
        status_code=303,
    )


@router.post("/bulk-delete")
async def email_template_bulk_delete(
    request: Request,
    auth_result: User | RedirectResponse = Depends(require_delete),
):
    """Delete multiple email templates."""
    if not isinstance(auth_result, User):
        return auth_result

    form = await request.form()
    template_ids_raw = form.getlist("template_ids")

    if not template_ids_raw:
        return RedirectResponse(
            url="/email-templates?error=No+templates+selected",
            status_code=303,
        )

    try:
        template_ids = [int(str(id_str)) for id_str in template_ids_raw if id_str]
    except ValueError:
        return RedirectResponse(
            url="/email-templates?error=Invalid+template+IDs",
            status_code=303,
        )

    if not template_ids:
        return RedirectResponse(
            url="/email-templates?error=No+valid+templates+selected",
            status_code=303,
        )

    deleted_count = 0
    for template_id in template_ids:
        if await mailler_client.delete_template(template_id):
            deleted_count += 1

    logger.info(
        "Email templates bulk deleted | user_id=%s deleted_count=%d",
        auth_result.id,
        deleted_count,
    )

    return RedirectResponse(
        url=f"/email-templates?success={deleted_count}+template(s)+deleted+successfully",
        status_code=303,
    )


@router.post("/{template_id}/delete")
async def email_template_delete(
    request: Request,
    template_id: int,
    auth_result: User | RedirectResponse = Depends(require_delete),
):
    """Delete an email template."""
    if not isinstance(auth_result, User):
        return auth_result

    success = await mailler_client.delete_template(template_id)

    if not success:
        return RedirectResponse(
            url="/email-templates?error=Failed+to+delete+template",
            status_code=303,
        )

    logger.info(
        "Email template deleted | user_id=%s template_id=%s",
        auth_result.id,
        template_id,
    )

    return RedirectResponse(
        url="/email-templates?success=Template+deleted+successfully",
        status_code=303,
    )
