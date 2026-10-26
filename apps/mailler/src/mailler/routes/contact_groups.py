# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Contact Group CRUD routes."""

import math

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from mailler.auth import AuthContext, require_scopes
from mailler.database import get_db
from mailler.logging import get_logger
from mailler.models.contact import Contact, ContactGroup, ContactGroupMember
from mailler.schemas.contact import (
    ContactGroupCreate,
    ContactGroupListItem,
    ContactGroupListResponse,
    ContactGroupResponse,
    ContactGroupUpdate,
    ContactListItem,
    ContactListResponse,
    GroupMembershipRequest,
    GroupMembershipResponse,
)

logger = get_logger(__name__)

router = APIRouter(prefix="/contact-groups", tags=["Contact Groups"])


@router.get("", response_model=ContactGroupListResponse)
async def list_contact_groups(
    page: int = Query(default=1, ge=1, description="Page number"),
    page_size: int = Query(default=20, ge=1, le=100, description="Items per page"),
    search: str | None = Query(default=None, description="Search in name and slug"),
    client_id: str | None = Query(
        default=None, description="Administrators only: restrict to one client"
    ),
    db: AsyncSession = Depends(get_db),
    auth: AuthContext = Depends(require_scopes("mailler:read")),
) -> ContactGroupListResponse:
    """List the contact groups of the calling client with pagination.

    Administrators see the groups of every client.

    Args:
        page: Page number (1-indexed)
        page_size: Items per page
        search: Optional search term
        client_id: Optional client filter, honoured for administrators only
        db: Database session
        auth: Authentication context

    Returns:
        Paginated list of contact groups
    """
    # Build query
    stmt = auth.restrict(select(ContactGroup), ContactGroup.client_id, client_id).order_by(
        ContactGroup.name.asc()
    )

    if search:
        search_pattern = f"%{search}%"
        stmt = stmt.where(
            (ContactGroup.name.ilike(search_pattern)) | (ContactGroup.slug.ilike(search_pattern))
        )

    # Get total count
    count_stmt = auth.restrict(
        select(func.count(ContactGroup.id)), ContactGroup.client_id, client_id
    )
    if search:
        count_stmt = count_stmt.where(
            (ContactGroup.name.ilike(search_pattern)) | (ContactGroup.slug.ilike(search_pattern))
        )

    total = (await db.execute(count_stmt)).scalar() or 0
    pages = math.ceil(total / page_size) if total > 0 else 1

    # Get page
    offset = (page - 1) * page_size
    stmt = stmt.offset(offset).limit(page_size)
    result = await db.execute(stmt)
    groups = result.scalars().all()

    items = [
        ContactGroupListItem(
            id=g.id,
            slug=g.slug,
            name=g.name,
            description=g.description,
            is_dynamic=g.is_dynamic,
            member_count=g.member_count,
            created_at=g.created_at,
        )
        for g in groups
    ]

    return ContactGroupListResponse(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
        pages=pages,
    )


@router.post("", response_model=ContactGroupResponse, status_code=201)
async def create_contact_group(
    request: ContactGroupCreate,
    client_id: str | None = Query(
        default=None, description="Administrators only: client the group is created for"
    ),
    db: AsyncSession = Depends(get_db),
    auth: AuthContext = Depends(require_scopes("mailler:write")),
) -> ContactGroupResponse:
    """Create a new contact group.

    Args:
        request: Group data
        db: Database session
        auth: Authentication context

    Returns:
        Created contact group

    Raises:
        HTTPException: If the slug already exists for the client
    """
    group = ContactGroup(
        client_id=auth.target_client_id(client_id),
        slug=request.slug,
        name=request.name,
        description=request.description,
        is_dynamic=request.is_dynamic,
        filter_criteria=request.filter_criteria,
    )

    try:
        db.add(group)
        await db.commit()
        await db.refresh(group)
    except IntegrityError:
        await db.rollback()
        raise HTTPException(
            status_code=409,
            detail=f"Group with slug '{request.slug}' already exists for this client",
        )

    logger.info(
        "Contact group created",
        extra={
            "group_id": group.id,
            "slug": group.slug,
            "user_id": str(auth.user.id) if auth.user.id else None,
        },
    )

    return ContactGroupResponse(
        id=group.id,
        client_id=group.client_id,
        slug=group.slug,
        name=group.name,
        description=group.description,
        is_dynamic=group.is_dynamic,
        filter_criteria=group.filter_criteria,
        member_count=group.member_count,
        created_at=group.created_at,
        updated_at=group.updated_at,
    )


@router.get("/{group_id}", response_model=ContactGroupResponse)
async def get_contact_group(
    group_id: int,
    db: AsyncSession = Depends(get_db),
    auth: AuthContext = Depends(require_scopes("mailler:read")),
) -> ContactGroupResponse:
    """Get contact group by ID.

    A group of another client is reported as not found.

    Args:
        group_id: Group ID
        db: Database session
        auth: Authentication context

    Returns:
        Contact group details

    Raises:
        HTTPException: If group not found
    """
    group = await db.get(ContactGroup, group_id)
    if not group or not auth.owns(group.client_id):
        raise HTTPException(status_code=404, detail="Contact group not found")

    return ContactGroupResponse(
        id=group.id,
        client_id=group.client_id,
        slug=group.slug,
        name=group.name,
        description=group.description,
        is_dynamic=group.is_dynamic,
        filter_criteria=group.filter_criteria,
        member_count=group.member_count,
        created_at=group.created_at,
        updated_at=group.updated_at,
    )


@router.get("/by-slug/{slug}", response_model=ContactGroupResponse)
async def get_contact_group_by_slug(
    slug: str,
    client_id: str | None = Query(
        default=None, description="Administrators only: client owning the group"
    ),
    db: AsyncSession = Depends(get_db),
    auth: AuthContext = Depends(require_scopes("mailler:read")),
) -> ContactGroupResponse:
    """Get a contact group of the calling client by slug.

    Args:
        slug: Group slug
        client_id: Client owning the group, administrators only
        db: Database session
        auth: Authentication context

    Returns:
        Contact group details

    Raises:
        HTTPException: If group not found
    """
    stmt = select(ContactGroup).where(
        ContactGroup.client_id == auth.target_client_id(client_id), ContactGroup.slug == slug
    )
    result = await db.execute(stmt)
    group = result.scalar_one_or_none()

    if not group:
        raise HTTPException(status_code=404, detail="Contact group not found")

    return ContactGroupResponse(
        id=group.id,
        client_id=group.client_id,
        slug=group.slug,
        name=group.name,
        description=group.description,
        is_dynamic=group.is_dynamic,
        filter_criteria=group.filter_criteria,
        member_count=group.member_count,
        created_at=group.created_at,
        updated_at=group.updated_at,
    )


@router.put("/{group_id}", response_model=ContactGroupResponse)
async def update_contact_group(
    group_id: int,
    request: ContactGroupUpdate,
    db: AsyncSession = Depends(get_db),
    auth: AuthContext = Depends(require_scopes("mailler:write")),
) -> ContactGroupResponse:
    """Update a contact group.

    Args:
        group_id: Group ID
        request: Updated group data
        db: Database session
        auth: Authentication context

    Returns:
        Updated contact group

    Raises:
        HTTPException: If group not found
    """
    group = await db.get(ContactGroup, group_id)
    if not group or not auth.owns(group.client_id):
        raise HTTPException(status_code=404, detail="Contact group not found")

    # Update fields if provided
    if request.name is not None:
        group.name = request.name
    if request.slug is not None:
        group.slug = request.slug
    if request.description is not None:
        group.description = request.description
    if request.is_dynamic is not None:
        group.is_dynamic = request.is_dynamic
    if request.filter_criteria is not None:
        group.filter_criteria = request.filter_criteria

    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(
            status_code=409, detail=f"Group with slug '{request.slug}' already exists"
        )
    await db.refresh(group)

    logger.info(
        "Contact group updated",
        extra={
            "group_id": group.id,
            "slug": group.slug,
            "user_id": str(auth.user.id) if auth.user.id else None,
        },
    )

    return ContactGroupResponse(
        id=group.id,
        client_id=group.client_id,
        slug=group.slug,
        name=group.name,
        description=group.description,
        is_dynamic=group.is_dynamic,
        filter_criteria=group.filter_criteria,
        member_count=group.member_count,
        created_at=group.created_at,
        updated_at=group.updated_at,
    )


@router.delete("/{group_id}", status_code=204)
async def delete_contact_group(
    group_id: int,
    db: AsyncSession = Depends(get_db),
    auth: AuthContext = Depends(require_scopes("mailler:write")),
) -> None:
    """Delete a contact group.

    Args:
        group_id: Group ID
        db: Database session
        auth: Authentication context

    Raises:
        HTTPException: If group not found
    """
    group = await db.get(ContactGroup, group_id)
    if not group or not auth.owns(group.client_id):
        raise HTTPException(status_code=404, detail="Contact group not found")

    logger.info(
        "Contact group deleted",
        extra={
            "group_id": group.id,
            "slug": group.slug,
            "user_id": str(auth.user.id) if auth.user.id else None,
        },
    )

    await db.delete(group)
    await db.commit()


@router.get("/{group_id}/contacts", response_model=ContactListResponse)
async def list_group_contacts(
    group_id: int,
    page: int = Query(default=1, ge=1, description="Page number"),
    page_size: int = Query(default=20, ge=1, le=100, description="Items per page"),
    search: str | None = Query(default=None, description="Search in email, first/last name"),
    db: AsyncSession = Depends(get_db),
    auth: AuthContext = Depends(require_scopes("mailler:read")),
) -> ContactListResponse:
    """List contacts in a group with pagination.

    Args:
        group_id: Group ID
        page: Page number (1-indexed)
        page_size: Items per page
        search: Optional search term
        db: Database session
        auth: Authentication context

    Returns:
        Paginated list of contacts

    Raises:
        HTTPException: If group not found
    """
    group = await db.get(ContactGroup, group_id)
    if not group or not auth.owns(group.client_id):
        raise HTTPException(status_code=404, detail="Contact group not found")

    # Build query
    stmt = (
        select(Contact)
        .join(ContactGroupMember)
        .where(ContactGroupMember.group_id == group_id)
        .order_by(Contact.email.asc())
    )

    # Apply search filter
    if search:
        search_pattern = f"%{search}%"
        stmt = stmt.where(
            (Contact.email.ilike(search_pattern))
            | (Contact.first_name.ilike(search_pattern))
            | (Contact.last_name.ilike(search_pattern))
        )

    # Get total count
    count_stmt = (
        select(func.count(Contact.id))
        .join(ContactGroupMember)
        .where(ContactGroupMember.group_id == group_id)
    )
    if search:
        count_stmt = count_stmt.where(
            (Contact.email.ilike(search_pattern))
            | (Contact.first_name.ilike(search_pattern))
            | (Contact.last_name.ilike(search_pattern))
        )

    total = (await db.execute(count_stmt)).scalar() or 0
    pages = math.ceil(total / page_size) if total > 0 else 1

    # Get page
    offset = (page - 1) * page_size
    stmt = stmt.offset(offset).limit(page_size)
    result = await db.execute(stmt)
    contacts = result.scalars().all()

    items = [
        ContactListItem(
            id=c.id,
            email=c.email,
            first_name=c.first_name,
            last_name=c.last_name,
            status=c.status,
            source=c.source,
            created_at=c.created_at,
        )
        for c in contacts
    ]

    return ContactListResponse(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
        pages=pages,
    )


@router.get("/{group_id}/available-contacts", response_model=ContactListResponse)
async def list_available_contacts(
    group_id: int,
    page: int = Query(default=1, ge=1, description="Page number"),
    page_size: int = Query(default=20, ge=1, le=100, description="Items per page"),
    search: str | None = Query(default=None, description="Search in email, first/last name"),
    db: AsyncSession = Depends(get_db),
    auth: AuthContext = Depends(require_scopes("mailler:read")),
) -> ContactListResponse:
    """List contacts NOT in a group (available for adding).

    Args:
        group_id: Group ID
        page: Page number (1-indexed)
        page_size: Items per page
        search: Optional search term
        db: Database session
        auth: Authentication context

    Returns:
        Paginated list of contacts not in the group

    Raises:
        HTTPException: If group not found
    """
    group = await db.get(ContactGroup, group_id)
    if not group or not auth.owns(group.client_id):
        raise HTTPException(status_code=404, detail="Contact group not found")

    # Subquery for contacts already in the group
    in_group_subquery = (
        select(ContactGroupMember.contact_id)
        .where(ContactGroupMember.group_id == group_id)
        .subquery()
    )

    # Build query for contacts NOT in group
    stmt = (
        select(Contact)
        .where(Contact.client_id == group.client_id)
        .where(Contact.id.not_in(select(in_group_subquery)))
        .where(Contact.status == "active")
        .order_by(Contact.email.asc())
    )

    # Apply search filter
    if search:
        search_pattern = f"%{search}%"
        stmt = stmt.where(
            (Contact.email.ilike(search_pattern))
            | (Contact.first_name.ilike(search_pattern))
            | (Contact.last_name.ilike(search_pattern))
        )

    # Get total count
    count_stmt = (
        select(func.count(Contact.id))
        .where(Contact.client_id == group.client_id)
        .where(Contact.id.not_in(select(in_group_subquery)))
        .where(Contact.status == "active")
    )
    if search:
        count_stmt = count_stmt.where(
            (Contact.email.ilike(search_pattern))
            | (Contact.first_name.ilike(search_pattern))
            | (Contact.last_name.ilike(search_pattern))
        )

    total = (await db.execute(count_stmt)).scalar() or 0
    pages = math.ceil(total / page_size) if total > 0 else 1

    # Get page
    offset = (page - 1) * page_size
    stmt = stmt.offset(offset).limit(page_size)
    result = await db.execute(stmt)
    contacts = result.scalars().all()

    items = [
        ContactListItem(
            id=c.id,
            email=c.email,
            first_name=c.first_name,
            last_name=c.last_name,
            status=c.status,
            source=c.source,
            created_at=c.created_at,
        )
        for c in contacts
    ]

    return ContactListResponse(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
        pages=pages,
    )


@router.post("/{group_id}/contacts", response_model=GroupMembershipResponse)
async def add_contacts_to_group(
    group_id: int,
    request: GroupMembershipRequest,
    db: AsyncSession = Depends(get_db),
    auth: AuthContext = Depends(require_scopes("mailler:write")),
) -> GroupMembershipResponse:
    """Add contacts to a group.

    Args:
        group_id: Group ID
        request: Contact IDs to add
        db: Database session
        auth: Authentication context

    Returns:
        Membership operation result

    Raises:
        HTTPException: If group not found
    """
    group = await db.get(ContactGroup, group_id)
    if not group or not auth.owns(group.client_id):
        raise HTTPException(status_code=404, detail="Contact group not found")

    added = 0
    skipped = 0

    for contact_id in request.contact_ids:
        # Check if contact exists
        contact = await db.get(Contact, contact_id)
        if not contact or contact.client_id != group.client_id:
            skipped += 1
            continue

        # Check if already a member
        existing = await db.execute(
            select(ContactGroupMember).where(
                (ContactGroupMember.contact_id == contact_id)
                & (ContactGroupMember.group_id == group_id)
            )
        )
        if existing.scalar_one_or_none():
            skipped += 1
            continue

        # Add membership
        membership = ContactGroupMember(contact_id=contact_id, group_id=group_id)
        db.add(membership)
        added += 1

    await db.commit()

    logger.info(
        "Contacts added to group",
        extra={
            "group_id": group_id,
            "added": added,
            "skipped": skipped,
            "user_id": str(auth.user.id) if auth.user.id else None,
        },
    )

    return GroupMembershipResponse(added=added, removed=0, skipped=skipped)


@router.delete("/{group_id}/contacts", response_model=GroupMembershipResponse)
async def remove_contacts_from_group(
    group_id: int,
    request: GroupMembershipRequest,
    db: AsyncSession = Depends(get_db),
    auth: AuthContext = Depends(require_scopes("mailler:write")),
) -> GroupMembershipResponse:
    """Remove contacts from a group.

    Args:
        group_id: Group ID
        request: Contact IDs to remove
        db: Database session
        auth: Authentication context

    Returns:
        Membership operation result

    Raises:
        HTTPException: If group not found
    """
    group = await db.get(ContactGroup, group_id)
    if not group or not auth.owns(group.client_id):
        raise HTTPException(status_code=404, detail="Contact group not found")

    removed = 0
    skipped = 0

    for contact_id in request.contact_ids:
        # Find membership
        result = await db.execute(
            select(ContactGroupMember).where(
                (ContactGroupMember.contact_id == contact_id)
                & (ContactGroupMember.group_id == group_id)
            )
        )
        membership = result.scalar_one_or_none()

        if membership:
            await db.delete(membership)
            removed += 1
        else:
            skipped += 1

    await db.commit()

    logger.info(
        "Contacts removed from group",
        extra={
            "group_id": group_id,
            "removed": removed,
            "skipped": skipped,
            "user_id": str(auth.user.id) if auth.user.id else None,
        },
    )

    return GroupMembershipResponse(added=0, removed=removed, skipped=skipped)
