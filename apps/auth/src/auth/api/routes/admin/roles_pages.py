# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Admin roles management HTML pages."""

import contextlib
import logging
import uuid
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Form, HTTPException, Query, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from auth.api.deps import get_db, get_templates, get_user_admin_permissions, require_scope
from auth.db.models.rbac import ADMIN_SCOPES, DEFAULT_ROLES, Role, RoleScope
from auth.db.models.user import User
from auth.services.role import role_service
from auth.services.scope import scope_service
from auth.services.user import UserService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/roles")

_role_service = role_service
_scope_service = scope_service
_user_service = UserService()

# Scope dependencies
require_roles_read = require_scope("roles:read", redirect_to_login=True)
require_roles_write = require_scope("roles:write", redirect_to_login=True)
require_roles_delete = require_scope("roles:delete", redirect_to_login=True)
require_roles_assign = require_scope("roles:assign", redirect_to_login=True)


def role_to_dict(role: Role, user_count: int = 0) -> dict:
    """Convert Role model to dictionary format."""
    scopes = role.get_all_scope_names()

    return {
        "id": str(role.id),
        "name": role.name,
        "description": role.description,
        "scopes": scopes,
        "is_system": role.is_system,
        "user_count": user_count,
        "created_at": role.created_at.isoformat() if role.created_at else None,
        "updated_at": role.updated_at.isoformat() if role.updated_at else None,
    }


@router.get("", response_class=HTMLResponse)
async def roles_list_page(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    auth: Annotated[tuple[User, list[Role]], Depends(require_roles_read)],
    page: Annotated[int, Query(ge=1)] = 1,
    search: Annotated[str | None, Query(max_length=255)] = None,
    is_system: Annotated[str | None, Query()] = None,
) -> HTMLResponse:
    """Roles list page.

    **Required scope:** `roles:read`

    **Example:**
    ```
    curl -H "Authorization: Bearer <token>" \\
      "https://auth.example.com/admin/roles?page=1&search=admin&is_system=true"
    ```
    """
    logger.debug("Admin page: listing roles")
    templates = get_templates()

    limit = 20

    is_system_filter: bool | None = None
    if is_system == "true":
        is_system_filter = True
    elif is_system == "false":
        is_system_filter = False

    roles, total = await _role_service.list(
        db,
        page=page,
        page_size=limit,
        search=search,
        is_system=is_system_filter,
        load_scopes=True,
        order_by_system_first=True,
    )

    # Get user counts for each role
    roles_list = []
    for role in roles:
        user_count = await _role_service.count_users_for_role(db, role.id)
        roles_list.append(role_to_dict(role, user_count))

    total_pages = (total + limit - 1) // limit

    success = request.query_params.get("success")
    error = request.query_params.get("error")

    user, roles_auth = auth
    permissions = get_user_admin_permissions(roles_auth)

    return templates.TemplateResponse(
        request=request,
        name="admin/roles/list.html",
        context={
            "active_section": "roles",
            "roles": roles_list,
            "total": total,
            "page": page,
            "total_pages": total_pages,
            "search": search or "",
            "is_system": is_system or "",
            "success": success,
            "error": error,
            "permissions": permissions,
        },
    )


@router.get("/create", response_class=HTMLResponse)
async def role_create_page(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    auth: Annotated[tuple[User, list[Role]], Depends(require_roles_write)],
) -> HTMLResponse:
    """Role creation form page.

    **Required scope:** `roles:write`

    **Example:**
    ```
    curl -H "Authorization: Bearer <token>" \\
      https://auth.example.com/admin/roles/create
    ```
    """
    logger.debug("Admin page: create role form")
    templates = get_templates()

    error = request.query_params.get("error")

    # Fetch active scopes via the service, grouped by category for the form.
    db_scopes = await _scope_service.list_active(db)

    scopes_by_category: dict[str, list[dict]] = {}
    for scope in db_scopes:
        if scope.category not in scopes_by_category:
            scopes_by_category[scope.category] = []
        scopes_by_category[scope.category].append(
            {
                "id": str(scope.id),
                "name": scope.name,
                "description": scope.description,
                "resource": scope.resource,
                "action": scope.action,
            }
        )

    user, roles_auth = auth
    permissions = get_user_admin_permissions(roles_auth)

    return templates.TemplateResponse(
        request=request,
        name="admin/roles/create.html",
        context={
            "active_section": "roles",
            "available_scopes": ADMIN_SCOPES,  # Hardcoded scopes
            "scopes_by_category": scopes_by_category,  # DB scopes grouped by category
            "error": error,
            "permissions": permissions,
        },
    )


@router.post("/create", response_class=RedirectResponse)
async def role_create_submit(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    auth: Annotated[tuple[User, list[Role]], Depends(require_roles_write)],
    name: Annotated[str, Form()],
    description: Annotated[str | None, Form()] = None,
    scopes: Annotated[list[str] | None, Form()] = None,
    wildcard_scopes: Annotated[str | None, Form()] = None,
) -> RedirectResponse:
    """Handle role creation form submission.

    **Required scope:** `roles:write`

    **Example:**
    ```
    curl -X POST -H "Authorization: Bearer <token>" \\
      -d "name=editor&description=Can+edit&scopes=users%3Aread" \\
      https://auth.example.com/admin/roles/create
    ```
    """
    logger.debug("Admin page: creating role name=%s", name)

    # Combine scopes from checkboxes and wildcard input
    all_scopes = list(scopes or [])
    if wildcard_scopes:
        additional = [s.strip() for s in wildcard_scopes.split(",") if s.strip()]
        all_scopes.extend(additional)

    # Remove duplicates while preserving order
    seen = set()
    unique_scopes = []
    for scope in all_scopes:
        if scope not in seen:
            seen.add(scope)
            unique_scopes.append(scope)

    try:
        role = await _role_service.create_role_by_scope_names(
            db,
            name=name,
            description=description or None,
            scope_names=unique_scopes,
        )
    except ValueError as exc:
        message = str(exc)
        if "already exists" in message.lower():
            return RedirectResponse(
                url="/admin/roles/create?error=Role+name+already+exists",
                status_code=status.HTTP_303_SEE_OTHER,
            )
        if message.startswith("Invalid scopes:"):
            # Preserve the original "Invalid scopes: a, b" formatting used by the
            # page (commas encoded as `+,+`).
            invalid_part = message[len("Invalid scopes: ") :]
            invalid_scopes = [s.strip() for s in invalid_part.split(",") if s.strip()]
            return RedirectResponse(
                url=f"/admin/roles/create?error=Invalid+scopes:+{',+'.join(invalid_scopes)}",
                status_code=status.HTTP_303_SEE_OTHER,
            )
        return RedirectResponse(
            url=f"/admin/roles/create?error={message}",
            status_code=status.HTTP_303_SEE_OTHER,
        )
    except Exception as e:
        logger.error("Admin page: failed to create role: %s", e)
        return RedirectResponse(
            url=f"/admin/roles/create?error={str(e)}",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    logger.info("Admin page: created role id=%s name=%s", role.id, role.name)
    return RedirectResponse(
        url=f"/admin/roles/{role.id}?success=Role+created+successfully",
        status_code=status.HTTP_303_SEE_OTHER,
    )


@router.get("/{role_id}", response_class=HTMLResponse)
async def role_detail_page(
    request: Request,
    role_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    auth: Annotated[tuple[User, list[Role]], Depends(require_roles_read)],
) -> HTMLResponse:
    """Role detail page.

    **Required scope:** `roles:read`

    **Example:**
    ```
    curl -H "Authorization: Bearer <token>" \\
      https://auth.example.com/admin/roles/550e8400-e29b-41d4-a716-446655440000
    ```
    """
    logger.debug("Admin page: viewing role id=%s", role_id)
    templates = get_templates()

    try:
        role_uuid = uuid.UUID(role_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid role ID format",
        )

    role = await _role_service.get_by_id(db, role_uuid, load_scopes=True)

    if not role:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Role not found",
        )

    # Get users with this role
    user_roles_data = await _role_service.list_users_for_role(db, role_uuid)

    users = []
    for user_role, user, email in user_roles_data:
        users.append(
            {
                "user_id": str(user.id),
                "email": email.email if email else None,
                "is_active": user.is_active,
                "assigned_at": user_role.created_at.isoformat() if user_role.created_at else None,
                "expires_at": user_role.expires_at.isoformat() if user_role.expires_at else None,
                "is_expired": user_role.is_expired,
            }
        )

    # Get explicit scopes assigned to this role
    explicit_scopes = [
        {
            "id": str(rs.scope.id),
            "name": rs.scope.name,
            "description": rs.scope.description,
            "category": rs.scope.category,
        }
        for rs in role.role_scopes
        if rs.scope and rs.scope.is_active
    ]

    role_dict = role_to_dict(role, len(users))
    role_dict["users"] = users
    role_dict["explicit_scopes"] = explicit_scopes

    # Fetch all available scopes from database for assignment
    db_scopes = await _scope_service.list_active(db)

    scopes_by_category: dict[str, list[dict]] = {}
    for scope in db_scopes:
        if scope.category not in scopes_by_category:
            scopes_by_category[scope.category] = []
        scopes_by_category[scope.category].append(
            {
                "id": str(scope.id),
                "name": scope.name,
                "description": scope.description,
            }
        )

    success = request.query_params.get("success")
    error = request.query_params.get("error")

    user, roles_auth = auth
    permissions = get_user_admin_permissions(roles_auth)

    # Debug logging for scope issues
    logger.info("DEBUG: User %s roles: %s", user.id, [r.name for r in roles_auth])
    for r in roles_auth:
        scope_names = r.get_all_scope_names()
        logger.info("DEBUG: Role %s scopes: %s", r.name, scope_names)
        logger.info(
            "DEBUG: Role %s has_scope('roles:assign'): %s", r.name, r.has_scope("roles:assign")
        )
    logger.info("DEBUG: permissions['roles:assign']: %s", permissions.get("roles:assign"))

    return templates.TemplateResponse(
        request=request,
        name="admin/roles/detail.html",
        context={
            "active_section": "roles",
            "role": role_dict,
            "available_scopes": ADMIN_SCOPES,
            "scopes_by_category": scopes_by_category,
            "success": success,
            "error": error,
            "permissions": permissions,
        },
    )


def _unique_scopes(scopes: list[str] | None, wildcard_scopes: str | None) -> list[str]:
    """Merge the checked scopes and the comma-separated ones, without duplicates."""
    merged = list(scopes or [])
    if wildcard_scopes:
        merged.extend(s.strip() for s in wildcard_scopes.split(",") if s.strip())
    return list(dict.fromkeys(merged))


@router.get("/{role_id}/edit", response_class=HTMLResponse, response_model=None)
async def role_edit_page(
    request: Request,
    role_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    auth: Annotated[tuple[User, list[Role]], Depends(require_roles_write)],
) -> HTMLResponse | RedirectResponse:
    """Role edit form page (description and scopes of a custom role).

    System roles cannot be modified: the page redirects to the role with an error.

    **Required scope:** `roles:write`

    **Example:**
    ```
    curl -H "Authorization: Bearer <token>" \\
      https://auth.example.com/admin/roles/550e8400-e29b-41d4-a716-446655440000/edit
    ```
    """
    logger.debug("Admin page: edit role form id=%s", role_id)
    templates = get_templates()

    try:
        role_uuid = uuid.UUID(role_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid role ID format",
        )

    role = await _role_service.get_by_id(db, role_uuid, load_scopes=True)

    if not role:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Role not found",
        )

    if role.is_system:
        return RedirectResponse(
            url=f"/admin/roles/{role_id}?error=System+roles+cannot+be+modified",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    held = role.get_all_scope_names()

    # The built-in scopes, then the other active scopes, then what the role holds that is neither.
    available_scopes: dict[str, str | None] = dict(ADMIN_SCOPES)
    for scope in await _scope_service.list_active(db):
        available_scopes.setdefault(scope.name, scope.description)
    for name in held:
        available_scopes.setdefault(name, None)

    user, roles_auth = auth
    permissions = get_user_admin_permissions(roles_auth)

    return templates.TemplateResponse(
        request=request,
        name="admin/roles/edit.html",
        context={
            "active_section": "roles",
            "role": role_to_dict(role),
            "available_scopes": available_scopes,
            "held_scopes": held,
            "error": request.query_params.get("error"),
            "permissions": permissions,
        },
    )


@router.post("/{role_id}/edit", response_class=RedirectResponse)
async def role_edit_submit(
    role_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    auth: Annotated[tuple[User, list[Role]], Depends(require_roles_write)],
    description: Annotated[str | None, Form()] = None,
    scopes: Annotated[list[str] | None, Form()] = None,
    wildcard_scopes: Annotated[str | None, Form()] = None,
) -> RedirectResponse:
    """Handle the role edit form: replace the description and the scopes of a custom role.

    **Required scope:** `roles:write`

    **Example:**
    ```
    curl -X POST -H "Authorization: Bearer <token>" \\
      -d "description=Can+edit&scopes=users%3Aread" \\
      https://auth.example.com/admin/roles/550e8400-e29b-41d4-a716-446655440000/edit
    ```
    """
    logger.debug("Admin page: updating role id=%s", role_id)

    try:
        role_uuid = uuid.UUID(role_id)
    except ValueError:
        return RedirectResponse(
            url="/admin/roles?error=Invalid+role+ID+format",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    role = await _role_service.get_by_id(db, role_uuid, load_scopes=True)

    if not role:
        return RedirectResponse(
            url="/admin/roles?error=Role+not+found",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    try:
        await _role_service.update_role_by_scope_names(
            db,
            role,
            description=description or None,
            scope_names=_unique_scopes(scopes, wildcard_scopes),
        )
    except ValueError as exc:
        message = str(exc)
        if message.startswith("System roles"):
            return RedirectResponse(
                url=f"/admin/roles/{role_id}?error=System+roles+cannot+be+modified",
                status_code=status.HTTP_303_SEE_OTHER,
            )
        return RedirectResponse(
            url=f"/admin/roles/{role_id}/edit?error={message}",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    logger.info("Admin page: updated role id=%s name=%s", role.id, role.name)
    return RedirectResponse(
        url=f"/admin/roles/{role_id}?success=Role+updated+successfully",
        status_code=status.HTTP_303_SEE_OTHER,
    )


@router.get("/{role_id}/assign", response_class=HTMLResponse)
async def role_assign_page(
    request: Request,
    role_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    auth: Annotated[tuple[User, list[Role]], Depends(require_roles_assign)],
    page: Annotated[int, Query(ge=1)] = 1,
    search: Annotated[str | None, Query(max_length=255)] = None,
) -> HTMLResponse:
    """Role assignment page.

    **Required scope:** `roles:assign`

    **Example:**
    ```
    curl -H "Authorization: Bearer <token>" \\
      "https://auth.example.com/admin/roles/550e8400-e29b-41d4-a716-446655440000/assign?search=alice"
    ```
    """
    logger.debug("Admin page: assign role id=%s", role_id)
    templates = get_templates()

    try:
        role_uuid = uuid.UUID(role_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid role ID format",
        )

    role = await _role_service.get_by_id(db, role_uuid, load_scopes=True)

    if not role:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Role not found",
        )

    # Get users to show for assignment
    limit = 20
    users_list = []
    total = 0
    total_pages = 0

    if search:
        # Search users by email through the user service
        rows, total = await _user_service.search_with_primary_email(
            db,
            search=search,
            page=page,
            page_size=limit,
        )
        total_pages = (total + limit - 1) // limit

        for candidate, email in rows:
            # Check if user already has this role
            has_role_assignment = await _role_service.get_user_role(db, role_uuid, candidate.id)
            has_role = has_role_assignment is not None

            # Get user's current roles
            current_roles = await _role_service.list_roles_for_user(db, candidate.id)
            user_roles = [r.name for r in current_roles]

            users_list.append(
                {
                    "id": str(candidate.id),
                    "email": email.email,
                    "is_active": candidate.is_active,
                    "has_role": has_role,
                    "roles": user_roles,
                }
            )

    error = request.query_params.get("error")

    user, roles_auth = auth
    permissions = get_user_admin_permissions(roles_auth)

    return templates.TemplateResponse(
        request=request,
        name="admin/roles/assign.html",
        context={
            "active_section": "roles",
            "role": role_to_dict(role),
            "users": users_list,
            "total": total,
            "page": page,
            "total_pages": total_pages,
            "search": search or "",
            "error": error,
            "permissions": permissions,
        },
    )


@router.post("/{role_id}/assign", response_class=RedirectResponse)
async def role_assign_submit(
    role_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    auth: Annotated[tuple[User, list[Role]], Depends(require_roles_assign)],
    user_id: Annotated[str, Form()],
    expires_at: Annotated[str | None, Form()] = None,
) -> RedirectResponse:
    """Handle role assignment form submission.

    **Required scope:** `roles:assign`

    **Example:**
    ```
    curl -X POST -H "Authorization: Bearer <token>" \\
      -d "user_id=660e8400-e29b-41d4-a716-446655440000" \\
      https://auth.example.com/admin/roles/550e8400-e29b-41d4-a716-446655440000/assign
    ```
    """
    logger.debug("Admin page: assigning role %s to user %s", role_id, user_id)

    try:
        role_uuid = uuid.UUID(role_id)
        user_uuid = uuid.UUID(user_id)
    except ValueError:
        return RedirectResponse(
            url=f"/admin/roles/{role_id}/assign?error=Invalid+ID+format",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    # Check role exists
    role = await _role_service.get_by_id(db, role_uuid)

    if not role:
        return RedirectResponse(
            url="/admin/roles?error=Role+not+found",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    # Check user exists
    target_user = await _user_service.get_by_id(db, user_uuid)

    if not target_user:
        return RedirectResponse(
            url=f"/admin/roles/{role_id}/assign?error=User+not+found",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    # Parse expiration date
    expiration = None
    if expires_at:
        with contextlib.suppress(ValueError):
            expiration = datetime.fromisoformat(expires_at).replace(tzinfo=UTC)

    try:
        await _role_service.assign_role_to_user(
            db,
            role_id=role_uuid,
            user_id=user_uuid,
            expires_at=expiration,
        )
    except ValueError:
        return RedirectResponse(
            url=f"/admin/roles/{role_id}/assign?error=User+already+has+this+role",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    logger.info("Admin page: assigned role %s to user %s", role.name, user_id)
    return RedirectResponse(
        url=f"/admin/roles/{role_id}?success=User+assigned+to+role+successfully",
        status_code=status.HTTP_303_SEE_OTHER,
    )


@router.post("/{role_id}/users/{user_id}/remove", response_class=RedirectResponse)
async def role_remove_user_submit(
    role_id: str,
    user_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    auth: Annotated[tuple[User, list[Role]], Depends(require_roles_assign)],
) -> RedirectResponse:
    """Handle removing user from role.

    **Required scope:** `roles:assign`

    **Example:**
    ```
    curl -X POST -H "Authorization: Bearer <token>" \\
      https://auth.example.com/admin/roles/550e8400-e29b-41d4-a716-446655440000/users/660e8400-e29b-41d4-a716-446655440000/remove
    ```
    """
    logger.debug("Admin page: removing user %s from role %s", user_id, role_id)

    try:
        role_uuid = uuid.UUID(role_id)
        user_uuid = uuid.UUID(user_id)
    except ValueError:
        return RedirectResponse(
            url=f"/admin/roles/{role_id}?error=Invalid+ID+format",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    # Find assignment
    user_role = await _role_service.get_user_role(db, role_uuid, user_uuid)

    if not user_role:
        return RedirectResponse(
            url=f"/admin/roles/{role_id}?error=Role+assignment+not+found",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    await _role_service.remove_role_from_user(db, user_role)

    logger.info("Admin page: removed user %s from role %s", user_id, role_id)
    return RedirectResponse(
        url=f"/admin/roles/{role_id}?success=User+removed+from+role+successfully",
        status_code=status.HTTP_303_SEE_OTHER,
    )


@router.post("/{role_id}/delete", response_class=RedirectResponse)
async def role_delete_submit(
    role_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    auth: Annotated[tuple[User, list[Role]], Depends(require_roles_delete)],
) -> RedirectResponse:
    """Handle role deletion.

    **Required scope:** `roles:delete`

    **Example:**
    ```
    curl -X POST -H "Authorization: Bearer <token>" \\
      https://auth.example.com/admin/roles/550e8400-e29b-41d4-a716-446655440000/delete
    ```
    """
    logger.debug("Admin page: deleting role id=%s", role_id)

    try:
        role_uuid = uuid.UUID(role_id)
    except ValueError:
        return RedirectResponse(
            url="/admin/roles?error=Invalid+role+ID+format",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    role = await _role_service.get_by_id(db, role_uuid)

    if not role:
        return RedirectResponse(
            url="/admin/roles?error=Role+not+found",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    try:
        await _role_service.delete_role(db, role)
    except ValueError:
        return RedirectResponse(
            url=f"/admin/roles/{role_id}?error=Cannot+delete+system+roles",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    logger.info("Admin page: deleted role id=%s", role_id)
    return RedirectResponse(
        url="/admin/roles?success=Role+deleted+successfully",
        status_code=status.HTTP_303_SEE_OTHER,
    )


@router.post("/seed", response_class=RedirectResponse)
async def seed_default_roles_submit(
    db: Annotated[AsyncSession, Depends(get_db)],
    auth: Annotated[tuple[User, list[Role]], Depends(require_roles_write)],
) -> RedirectResponse:
    """Seed default system roles.

    **Required scope:** `roles:write`

    **Example:**
    ```
    curl -X POST -H "Authorization: Bearer <token>" \\
      https://auth.example.com/admin/roles/seed
    ```
    """
    logger.debug("Admin page: seeding default roles")

    created = await _seed_default_roles(db)

    logger.info("Admin page: seeded %d default roles: %s", len(created), ", ".join(created))

    if created:
        return RedirectResponse(
            url=f"/admin/roles?success=Created+{len(created)}+role(s):+{',+'.join(created)}",
            status_code=status.HTTP_303_SEE_OTHER,
        )
    return RedirectResponse(
        url="/admin/roles?success=All+default+roles+already+exist",
        status_code=status.HTTP_303_SEE_OTHER,
    )


async def _seed_default_roles(db: AsyncSession) -> list[str]:
    """Seed ``DEFAULT_ROLES`` using the scope cache pattern expected by tests.

    Pre-fetches the scope catalog via :class:`ScopeService` then iterates over
    ``DEFAULT_ROLES``. For each missing role, creates it via
    :class:`RoleService` using the repository write primitives — no direct
    ``db.execute`` or ``select()`` is used here.
    """
    scopes_catalog = await _scope_service.list_active(db)
    db_scopes = {s.name: s for s in scopes_catalog}

    created: list[str] = []
    for name, config in DEFAULT_ROLES.items():
        existing = await _role_service.get_by_name(db, name)
        if existing is not None:
            logger.debug("Role %s already exists, skipping", name)
            continue

        role = Role(
            name=name,
            description=config["description"],
            is_system=config["is_system"],
        )
        await _role_service.add_role(db, role)

        for scope_name in config["scopes"]:  # type: ignore[attr-defined]
            if scope_name in db_scopes:
                role_scope = RoleScope(
                    role_id=role.id,
                    scope_id=db_scopes[scope_name].id,
                )
                await _role_service.add_role_scope(db, role_scope)

        created.append(name)

    await db.commit()
    return created
