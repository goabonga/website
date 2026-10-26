# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""System Prompt CRUD routes with versioning support.

Scopes required:
- prompts:read - View prompts
- prompts:write - Create, update prompts
- prompts:delete - Delete prompts
"""

import json

from fastapi import APIRouter, Depends, Form, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from internal import TEMPLATES_DIR
from internal.auth.dependencies import (
    require_resource_scopes_or_redirect,
    require_scope_or_redirect,
)
from internal.auth.models import User
from internal.config import settings
from internal.database import get_db
from internal.logging import get_logger
from internal.models.prompt import SystemPrompt, SystemPromptVersion

router = APIRouter(prefix="/prompts", tags=["prompts"])
templates = Jinja2Templates(directory=TEMPLATES_DIR)
logger = get_logger(__name__)

# Use resource-level scope request to get all permissions at once for proper UI display
# Also request vpn:admin to show VPN link in navigation if user has permission
require_read = require_resource_scopes_or_redirect(
    "prompts", extra_scopes=["vpn:admin", "billing:read"]
)
require_write = require_scope_or_redirect("prompts:write")
require_delete = require_scope_or_redirect("prompts:delete")

DEFAULT_PROMPT_SLUG = "default"


async def ensure_default_prompt(db: AsyncSession) -> SystemPrompt:
    """Ensure a default prompt exists."""
    result = await db.execute(select(SystemPrompt).where(SystemPrompt.is_default.is_(True)))
    prompt = result.scalar_one_or_none()

    if not prompt:
        # Create default prompt
        prompt = SystemPrompt(
            slug=DEFAULT_PROMPT_SLUG,
            name="Default Assistant",
            description="Default system prompt for the AI assistant",
            is_default=True,
        )
        db.add(prompt)
        await db.flush()

        # Create initial version
        version = SystemPromptVersion(
            prompt_id=prompt.id,
            version=1,
            content="""You are a helpful AI assistant. You provide accurate, helpful, and concise responses.

When responding:
- Be direct and helpful
- If you used information from the knowledge base, integrate it naturally
- If you don't know something, say so honestly
- Keep responses focused and relevant""",
            metadata_={},
            is_current=True,
        )
        db.add(version)
        await db.commit()
        await db.refresh(prompt)
        logger.info("Created default prompt: %s", DEFAULT_PROMPT_SLUG)

    return prompt


# =============================================================================
# AI-Powered Generation Routes (must be before /{prompt_id} routes)
# =============================================================================


def get_generator_service():
    """Get prompt generator service if OpenAI is configured."""
    if not settings.openai_api_key:
        return None
    from internal.services.prompt_generator import PromptGeneratorService

    return PromptGeneratorService()


@router.get("/generate", response_class=HTMLResponse)
async def prompt_generate_form(
    request: Request,
    db: AsyncSession = Depends(get_db),
    auth_result: User | RedirectResponse = Depends(require_write),
):
    """Show form to generate a prompt using AI."""
    if not isinstance(auth_result, User):
        return auth_result

    user = auth_result

    logger.info(
        "Prompt generate form accessed | user_id=%s client_id=%s",
        user.id,
        settings.oauth2_client_id,
    )

    if not settings.openai_api_key:
        return RedirectResponse(
            url="/prompts?error=OpenAI+not+configured",
            status_code=303,
        )

    return templates.TemplateResponse(
        request=request,
        name="admin/prompts/generate.html",
        context={
            "request": request,
            "active_section": "prompts",
            "user": user,
        },
    )


@router.post("/generate")
async def prompt_generate(
    request: Request,
    description: str = Form(...),
    tone: str = Form("professional"),
    focus_areas: str = Form(""),
    constraints: str = Form(""),
    required_scopes: str = Form(""),
    is_default: bool = Form(False),
    db: AsyncSession = Depends(get_db),
    auth_result: User | RedirectResponse = Depends(require_write),
):
    """Generate a prompt using AI from description."""
    if not isinstance(auth_result, User):
        return auth_result

    generator = get_generator_service()
    if not generator:
        return RedirectResponse(
            url="/prompts/generate?error=OpenAI+not+configured",
            status_code=303,
        )

    description = description.strip()
    tone = tone.strip()
    focus_areas_val = focus_areas.strip() or None
    constraints_val = constraints.strip() or None
    required_scopes = required_scopes.strip()

    if len(description) < 20:
        return RedirectResponse(
            url="/prompts/generate?error=Description+too+short+(min+20+characters)",
            status_code=303,
        )

    try:
        # Generate prompt using AI
        generated = await generator.generate_prompt(
            description=description,
            tone=tone,
            focus_areas=focus_areas_val,
            constraints=constraints_val,
        )

        if not generated:
            return RedirectResponse(
                url="/prompts/generate?error=Failed+to+generate+prompt",
                status_code=303,
            )

        # Store generated content in session/query params for the new form
        # We'll pass the generated content to the new prompt form
        import urllib.parse

        encoded_content = urllib.parse.quote(generated.get("content", ""))
        encoded_name = urllib.parse.quote(generated.get("name", "Generated Prompt"))
        encoded_slug = urllib.parse.quote(generated.get("slug", "generated-prompt"))
        encoded_desc = urllib.parse.quote(generated.get("description", ""))
        encoded_scopes = urllib.parse.quote(required_scopes)
        is_default_str = "1" if is_default else "0"

        logger.info(
            "Prompt generated via AI | user_id=%s client_id=%s slug=%s",
            auth_result.id,
            settings.oauth2_client_id,
            encoded_slug,
        )

        return RedirectResponse(
            url=f"/prompts/new?generated=1&name={encoded_name}&slug={encoded_slug}&description={encoded_desc}&content={encoded_content}&scopes={encoded_scopes}&is_default={is_default_str}",
            status_code=303,
        )

    except Exception as e:
        logger.error("Failed to generate prompt: %s", e)
        return RedirectResponse(
            url=f"/prompts/generate?error=Generation+failed:+{str(e)[:50]}",
            status_code=303,
        )


# =============================================================================
# Standard CRUD Routes
# =============================================================================


@router.get("", response_class=HTMLResponse)
async def prompt_list(
    request: Request,
    page: int = Query(1, ge=1),
    search: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
    auth_result: User | RedirectResponse = Depends(require_read),
):
    """List all prompts with pagination and search."""
    if not isinstance(auth_result, User):
        return auth_result

    user = auth_result

    logger.info(
        "Prompt list accessed | user_id=%s client_id=%s page=%d search=%s",
        user.id,
        settings.oauth2_client_id,
        page,
        search,
    )

    # Ensure default prompt exists
    await ensure_default_prompt(db)

    limit = 20
    offset = (page - 1) * limit

    # Build base query
    base_query = select(SystemPrompt)

    # Apply search filter
    if search:
        search_pattern = f"%{search}%"
        base_query = base_query.where(
            SystemPrompt.name.ilike(search_pattern)
            | SystemPrompt.slug.ilike(search_pattern)
            | SystemPrompt.description.ilike(search_pattern)
        )

    # Count total
    count_query = select(func.count()).select_from(
        base_query.with_only_columns(SystemPrompt.id).subquery()
    )
    total = await db.scalar(count_query) or 0
    total_pages = (total + limit - 1) // limit if total > 0 else 1

    # Get paginated results
    query = base_query.order_by(SystemPrompt.name).offset(offset).limit(limit)
    result = await db.execute(query)
    prompts = list(result.scalars().all())

    return templates.TemplateResponse(
        request=request,
        name="admin/prompts/list.html",
        context={
            "request": request,
            "active_section": "prompts",
            "user": user,
            "prompts": prompts,
            "total": total,
            "page": page,
            "total_pages": total_pages,
            "search": search,
            "success": request.query_params.get("success"),
            "error": request.query_params.get("error"),
            "openai_configured": bool(settings.openai_api_key),
        },
    )


@router.get("/new", response_class=HTMLResponse)
async def prompt_new(
    request: Request,
    auth_result: User | RedirectResponse = Depends(require_write),
):
    """Show form to create a new prompt."""
    if not isinstance(auth_result, User):
        return auth_result

    user = auth_result

    logger.info(
        "Prompt new form accessed | user_id=%s client_id=%s",
        user.id,
        settings.oauth2_client_id,
    )

    # Check for generated content from AI
    generated = request.query_params.get("generated") == "1"

    return templates.TemplateResponse(
        request=request,
        name="admin/prompts/form.html",
        context={
            "request": request,
            "active_section": "prompts",
            "user": user,
            "prompt": None,
            "is_edit": False,
            "generated": generated,
            "prefill_name": request.query_params.get("name", ""),
            "prefill_slug": request.query_params.get("slug", ""),
            "prefill_description": request.query_params.get("description", ""),
            "prefill_content": request.query_params.get("content", ""),
        },
    )


@router.post("/new")
async def prompt_create(
    request: Request,
    slug: str = Form(...),
    name: str = Form(...),
    content: str = Form(...),
    description: str = Form(""),
    required_scopes: str = Form(""),
    is_default: bool = Form(False),
    metadata_json: str = Form("{}"),
    db: AsyncSession = Depends(get_db),
    auth_result: User | RedirectResponse = Depends(require_write),
):
    """Create a new prompt with initial version."""
    if not isinstance(auth_result, User):
        return auth_result

    slug = slug.strip().lower()
    name = name.strip()
    content = content.strip()
    desc_val = description.strip() or None

    # Parse metadata JSON
    try:
        metadata = json.loads(metadata_json) if metadata_json else {}
    except json.JSONDecodeError:
        return RedirectResponse(
            url="/prompts/new?error=Invalid+JSON+in+metadata+field",
            status_code=303,
        )

    # Parse scopes (comma-separated)
    scopes_list = None
    if required_scopes.strip():
        scopes_list = [s.strip() for s in required_scopes.split(",") if s.strip()]

    # Check if slug already exists
    result = await db.execute(select(SystemPrompt).where(SystemPrompt.slug == slug))
    if result.scalar_one_or_none():
        return RedirectResponse(
            url=f"/prompts/new?error=Prompt+with+slug+'{slug}'+already+exists",
            status_code=303,
        )

    # If setting as default, unset any existing default
    if is_default:
        await db.execute(
            update(SystemPrompt).where(SystemPrompt.is_default.is_(True)).values(is_default=False)
        )

    # Create prompt
    prompt = SystemPrompt(
        slug=slug,
        name=name,
        description=desc_val,
        required_scopes=scopes_list,
        is_default=is_default,
    )
    db.add(prompt)
    await db.flush()

    # Create initial version
    version = SystemPromptVersion(
        prompt_id=prompt.id,
        version=1,
        content=content,
        metadata_=metadata,
        is_current=True,
    )
    db.add(version)

    await db.commit()

    logger.info(
        "Prompt created | user_id=%s client_id=%s prompt_id=%s slug=%s",
        auth_result.id,
        settings.oauth2_client_id,
        prompt.id,
        prompt.slug,
    )

    return RedirectResponse(
        url="/prompts?success=Prompt+created+successfully",
        status_code=303,
    )


@router.get("/{prompt_id}", response_class=HTMLResponse)
async def prompt_detail(
    request: Request,
    prompt_id: int,
    db: AsyncSession = Depends(get_db),
    auth_result: User | RedirectResponse = Depends(require_read),
):
    """View prompt detail with version history."""
    if not isinstance(auth_result, User):
        return auth_result

    user = auth_result

    logger.info(
        "Prompt detail accessed | user_id=%s client_id=%s prompt_id=%s",
        user.id,
        settings.oauth2_client_id,
        prompt_id,
    )

    result = await db.execute(select(SystemPrompt).where(SystemPrompt.id == prompt_id))
    prompt = result.scalar_one_or_none()

    if not prompt:
        return RedirectResponse(
            url="/prompts?error=Prompt+not+found",
            status_code=303,
        )

    return templates.TemplateResponse(
        request=request,
        name="admin/prompts/detail.html",
        context={
            "request": request,
            "active_section": "prompts",
            "user": user,
            "prompt": prompt,
            "current_version": prompt.get_current_version(),
            "success": request.query_params.get("success"),
            "error": request.query_params.get("error"),
        },
    )


@router.get("/{prompt_id}/edit", response_class=HTMLResponse)
async def prompt_edit(
    request: Request,
    prompt_id: int,
    db: AsyncSession = Depends(get_db),
    auth_result: User | RedirectResponse = Depends(require_write),
):
    """Show form to edit a prompt (creates new version)."""
    if not isinstance(auth_result, User):
        return auth_result

    user = auth_result

    logger.info(
        "Prompt edit form accessed | user_id=%s client_id=%s prompt_id=%s",
        user.id,
        settings.oauth2_client_id,
        prompt_id,
    )

    result = await db.execute(select(SystemPrompt).where(SystemPrompt.id == prompt_id))
    prompt = result.scalar_one_or_none()

    if not prompt:
        return RedirectResponse(
            url="/prompts?error=Prompt+not+found",
            status_code=303,
        )

    return templates.TemplateResponse(
        request=request,
        name="admin/prompts/form.html",
        context={
            "request": request,
            "active_section": "prompts",
            "user": user,
            "prompt": prompt,
            "is_edit": True,
            "current_version": prompt.get_current_version(),
            "generated": False,
            "prefill_name": "",
            "prefill_slug": "",
            "prefill_description": "",
            "prefill_content": "",
        },
    )


@router.post("/{prompt_id}/edit")
async def prompt_update(
    request: Request,
    prompt_id: int,
    slug: str = Form(...),
    name: str = Form(...),
    content: str = Form(...),
    description: str = Form(""),
    required_scopes: str = Form(""),
    is_default: bool = Form(False),
    metadata_json: str = Form("{}"),
    db: AsyncSession = Depends(get_db),
    auth_result: User | RedirectResponse = Depends(require_write),
):
    """Update a prompt (creates new version if content changed)."""
    if not isinstance(auth_result, User):
        return auth_result

    result = await db.execute(select(SystemPrompt).where(SystemPrompt.id == prompt_id))
    prompt = result.scalar_one_or_none()

    if not prompt:
        return RedirectResponse(
            url="/prompts?error=Prompt+not+found",
            status_code=303,
        )

    slug = slug.strip().lower()
    name = name.strip()
    content = content.strip()
    desc_val = description.strip() or None

    # Parse metadata JSON
    try:
        metadata = json.loads(metadata_json) if metadata_json else {}
    except json.JSONDecodeError:
        return RedirectResponse(
            url=f"/prompts/{prompt_id}/edit?error=Invalid+JSON+in+metadata+field",
            status_code=303,
        )

    # Parse scopes (comma-separated)
    scopes_list = None
    if required_scopes.strip():
        scopes_list = [s.strip() for s in required_scopes.split(",") if s.strip()]

    # Check if new slug conflicts with another prompt
    if slug != prompt.slug:
        existing = await db.execute(select(SystemPrompt).where(SystemPrompt.slug == slug))
        if existing.scalar_one_or_none():
            return RedirectResponse(
                url=f"/prompts/{prompt_id}/edit?error=Prompt+with+slug+'{slug}'+already+exists",
                status_code=303,
            )

    # If setting as default, unset any existing default
    if is_default and not prompt.is_default:
        await db.execute(
            update(SystemPrompt).where(SystemPrompt.is_default.is_(True)).values(is_default=False)
        )

    # Update prompt metadata
    prompt.slug = slug
    prompt.name = name
    prompt.description = desc_val
    prompt.required_scopes = scopes_list
    prompt.is_default = is_default

    # Check if content changed - if so, create new version
    current_version = prompt.get_current_version()
    if not current_version or current_version.content != content:
        # Get max version number
        max_version = 0
        for v in prompt.versions:
            if v.version > max_version:
                max_version = v.version

        # Unset current on all versions
        await db.execute(
            update(SystemPromptVersion)
            .where(SystemPromptVersion.prompt_id == prompt_id)
            .values(is_current=False)
        )

        # Create new version
        new_version = SystemPromptVersion(
            prompt_id=prompt_id,
            version=max_version + 1,
            content=content,
            metadata_=metadata,
            is_current=True,
        )
        db.add(new_version)
        logger.info(
            "Prompt new version created | user_id=%s client_id=%s prompt_id=%s version=%d",
            auth_result.id,
            settings.oauth2_client_id,
            prompt.id,
            max_version + 1,
        )

    await db.commit()

    logger.info(
        "Prompt updated | user_id=%s client_id=%s prompt_id=%s slug=%s",
        auth_result.id,
        settings.oauth2_client_id,
        prompt.id,
        prompt.slug,
    )

    return RedirectResponse(
        url=f"/prompts/{prompt_id}?success=Prompt+updated+successfully",
        status_code=303,
    )


@router.post("/{prompt_id}/version/{version_id}/activate")
async def prompt_activate_version(
    request: Request,
    prompt_id: int,
    version_id: int,
    db: AsyncSession = Depends(get_db),
    auth_result: User | RedirectResponse = Depends(require_write),
):
    """Activate a specific version of a prompt."""
    if not isinstance(auth_result, User):
        return auth_result

    # Verify version belongs to this prompt
    result = await db.execute(
        select(SystemPromptVersion).where(
            SystemPromptVersion.id == version_id,
            SystemPromptVersion.prompt_id == prompt_id,
        )
    )
    version = result.scalar_one_or_none()

    if not version:
        return RedirectResponse(
            url=f"/prompts/{prompt_id}?error=Version+not+found",
            status_code=303,
        )

    # Unset current on all versions
    await db.execute(
        update(SystemPromptVersion)
        .where(SystemPromptVersion.prompt_id == prompt_id)
        .values(is_current=False)
    )

    # Set this version as current
    version.is_current = True
    await db.commit()

    logger.info(
        "Prompt version activated | user_id=%s client_id=%s prompt_id=%s version=%d",
        auth_result.id,
        settings.oauth2_client_id,
        prompt_id,
        version.version,
    )

    return RedirectResponse(
        url=f"/prompts/{prompt_id}?success=Version+{version.version}+activated",
        status_code=303,
    )


@router.post("/{prompt_id}/version/{version_id}/delete")
async def prompt_version_delete(
    request: Request,
    prompt_id: int,
    version_id: int,
    db: AsyncSession = Depends(get_db),
    auth_result: User | RedirectResponse = Depends(require_delete),
):
    """Delete a specific version of a prompt."""
    if not isinstance(auth_result, User):
        return auth_result

    # Verify version belongs to this prompt
    result = await db.execute(
        select(SystemPromptVersion).where(
            SystemPromptVersion.id == version_id,
            SystemPromptVersion.prompt_id == prompt_id,
        )
    )
    version = result.scalar_one_or_none()

    if not version:
        return RedirectResponse(
            url=f"/prompts/{prompt_id}?error=Version+not+found",
            status_code=303,
        )

    # Prevent deleting the current version
    if version.is_current:
        return RedirectResponse(
            url=f"/prompts/{prompt_id}?error=Cannot+delete+the+current+version",
            status_code=303,
        )

    version_num = version.version
    await db.delete(version)
    await db.commit()

    logger.info(
        "Prompt version deleted | user_id=%s client_id=%s prompt_id=%s version=%d",
        auth_result.id,
        settings.oauth2_client_id,
        prompt_id,
        version_num,
    )

    return RedirectResponse(
        url=f"/prompts/{prompt_id}?success=Version+{version_num}+deleted",
        status_code=303,
    )


@router.post("/{prompt_id}/versions/bulk-delete")
async def prompt_versions_bulk_delete(
    request: Request,
    prompt_id: int,
    db: AsyncSession = Depends(get_db),
    auth_result: User | RedirectResponse = Depends(require_delete),
):
    """Delete multiple versions of a prompt."""
    if not isinstance(auth_result, User):
        return auth_result

    form = await request.form()
    # The page sends the selection as one comma-separated value
    version_ids_raw = form.getlist("version_ids")

    if not version_ids_raw:
        return RedirectResponse(
            url=f"/prompts/{prompt_id}?error=No+versions+selected",
            status_code=303,
        )

    try:
        version_ids = [
            int(id_str)
            for raw in version_ids_raw
            for id_str in str(raw).replace(" ", "").split(",")
            if id_str
        ]
    except ValueError:
        return RedirectResponse(
            url=f"/prompts/{prompt_id}?error=Invalid+version+IDs",
            status_code=303,
        )

    result = await db.execute(
        select(SystemPromptVersion).where(
            SystemPromptVersion.id.in_(version_ids),
            SystemPromptVersion.prompt_id == prompt_id,
        )
    )
    versions = result.scalars().all()

    if not versions:
        return RedirectResponse(
            url=f"/prompts/{prompt_id}?error=No+versions+found",
            status_code=303,
        )

    deleted_count = 0
    skipped_current = 0
    for version in versions:
        if version.is_current:
            skipped_current += 1
            continue
        await db.delete(version)
        deleted_count += 1

    await db.commit()

    logger.info(
        "Prompt versions bulk deleted | user_id=%s client_id=%s prompt_id=%s deleted_count=%d skipped_current=%d",
        auth_result.id,
        settings.oauth2_client_id,
        prompt_id,
        deleted_count,
        skipped_current,
    )

    if skipped_current > 0:
        return RedirectResponse(
            url=f"/prompts/{prompt_id}?success={deleted_count}+version(s)+deleted,+{skipped_current}+skipped+(current)",
            status_code=303,
        )

    return RedirectResponse(
        url=f"/prompts/{prompt_id}?success={deleted_count}+version(s)+deleted+successfully",
        status_code=303,
    )


@router.post("/bulk-delete")
async def prompt_bulk_delete(
    request: Request,
    db: AsyncSession = Depends(get_db),
    auth_result: User | RedirectResponse = Depends(require_delete),
):
    """Delete multiple prompts."""
    if not isinstance(auth_result, User):
        return auth_result

    form = await request.form()
    # The page sends the selection as one comma-separated value
    prompt_ids_raw = form.getlist("prompt_ids")

    if not prompt_ids_raw:
        return RedirectResponse(
            url="/prompts?error=No+prompts+selected",
            status_code=303,
        )

    try:
        prompt_ids = [
            int(id_str)
            for raw in prompt_ids_raw
            for id_str in str(raw).replace(" ", "").split(",")
            if id_str
        ]
    except ValueError:
        return RedirectResponse(
            url="/prompts?error=Invalid+prompt+IDs",
            status_code=303,
        )

    result = await db.execute(select(SystemPrompt).where(SystemPrompt.id.in_(prompt_ids)))
    prompts = result.scalars().all()

    if not prompts:
        return RedirectResponse(
            url="/prompts?error=No+prompts+found",
            status_code=303,
        )

    deleted_count = 0
    skipped_default = 0
    for prompt in prompts:
        if prompt.is_default:
            skipped_default += 1
            continue
        await db.delete(prompt)
        deleted_count += 1

    await db.commit()

    logger.info(
        "Prompts bulk deleted | user_id=%s client_id=%s deleted_count=%d skipped_default=%d",
        auth_result.id,
        settings.oauth2_client_id,
        deleted_count,
        skipped_default,
    )

    if skipped_default > 0:
        return RedirectResponse(
            url=f"/prompts?success={deleted_count}+prompt(s)+deleted,+{skipped_default}+skipped+(default)",
            status_code=303,
        )

    return RedirectResponse(
        url=f"/prompts?success={deleted_count}+prompt(s)+deleted+successfully",
        status_code=303,
    )


@router.post("/{prompt_id}/delete")
async def prompt_delete(
    request: Request,
    prompt_id: int,
    db: AsyncSession = Depends(get_db),
    auth_result: User | RedirectResponse = Depends(require_delete),
):
    """Delete a prompt."""
    if not isinstance(auth_result, User):
        return auth_result

    result = await db.execute(select(SystemPrompt).where(SystemPrompt.id == prompt_id))
    prompt = result.scalar_one_or_none()

    if not prompt:
        return RedirectResponse(
            url="/prompts?error=Prompt+not+found",
            status_code=303,
        )

    # Prevent deleting the default prompt
    if prompt.is_default:
        return RedirectResponse(
            url="/prompts?error=Cannot+delete+the+default+prompt",
            status_code=303,
        )

    await db.delete(prompt)
    await db.commit()

    logger.info(
        "Prompt deleted | user_id=%s client_id=%s prompt_id=%s slug=%s",
        auth_result.id,
        settings.oauth2_client_id,
        prompt_id,
        prompt.slug,
    )

    return RedirectResponse(
        url="/prompts?success=Prompt+deleted+successfully",
        status_code=303,
    )
