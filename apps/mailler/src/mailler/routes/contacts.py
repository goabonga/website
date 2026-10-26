# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Contact CRUD routes."""

import math
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from mailler.auth import AuthContext, require_scopes
from mailler.database import get_db
from mailler.logging import get_logger
from mailler.models.contact import Contact, ContactGroupMember, ContactStatus
from mailler.schemas.contact import (
    BulkContactCreate,
    BulkContactResponse,
    ContactCreate,
    ContactListItem,
    ContactListResponse,
    ContactResponse,
    ContactUpdate,
)

logger = get_logger(__name__)

router = APIRouter(prefix="/contacts", tags=["Contacts"])


@router.get("", response_model=ContactListResponse)
async def list_contacts(
    page: int = Query(default=1, ge=1, description="Page number"),
    page_size: int = Query(default=20, ge=1, le=100, description="Items per page"),
    status: str | None = Query(default=None, description="Filter by status"),
    search: str | None = Query(default=None, description="Search in email and name"),
    group_id: int | None = Query(default=None, description="Filter by group membership"),
    client_id: str | None = Query(
        default=None, description="Administrators only: restrict to one client"
    ),
    db: AsyncSession = Depends(get_db),
    auth: AuthContext = Depends(require_scopes("mailler:read")),
) -> ContactListResponse:
    """List the contacts of the calling client with pagination.

    Administrators see the contacts of every client.

    Args:
        page: Page number (1-indexed)
        page_size: Items per page
        status: Optional status filter
        search: Optional search term
        group_id: Optional filter by group membership
        client_id: Optional client filter, honoured for administrators only
        db: Database session
        auth: Authentication context

    Returns:
        Paginated list of contacts
    """
    # Build query
    stmt = auth.restrict(select(Contact), Contact.client_id, client_id).order_by(
        Contact.created_at.desc()
    )

    if status:
        stmt = stmt.where(Contact.status == status)
    if search:
        search_pattern = f"%{search}%"
        stmt = stmt.where(
            (Contact.email.ilike(search_pattern))
            | (Contact.first_name.ilike(search_pattern))
            | (Contact.last_name.ilike(search_pattern))
        )
    if group_id:
        stmt = stmt.join(ContactGroupMember).where(ContactGroupMember.group_id == group_id)

    # Get total count
    count_stmt = auth.restrict(select(func.count(Contact.id)), Contact.client_id, client_id)
    if status:
        count_stmt = count_stmt.where(Contact.status == status)
    if search:
        count_stmt = count_stmt.where(
            (Contact.email.ilike(search_pattern))
            | (Contact.first_name.ilike(search_pattern))
            | (Contact.last_name.ilike(search_pattern))
        )
    if group_id:
        count_stmt = count_stmt.join(ContactGroupMember).where(
            ContactGroupMember.group_id == group_id
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


@router.post("", response_model=ContactResponse, status_code=201)
async def create_contact(
    request: ContactCreate,
    client_id: str | None = Query(
        default=None, description="Administrators only: client the contact is created for"
    ),
    db: AsyncSession = Depends(get_db),
    auth: AuthContext = Depends(require_scopes("mailler:write")),
) -> ContactResponse:
    """Create a new contact.

    Args:
        request: Contact data
        db: Database session
        auth: Authentication context

    Returns:
        Created contact

    Raises:
        HTTPException: If the email already exists for the client
    """
    contact = Contact(
        client_id=auth.target_client_id(client_id),
        email=request.email,
        first_name=request.first_name,
        last_name=request.last_name,
        source=request.source,
        custom_fields=request.custom_fields or {},
        status=ContactStatus.ACTIVE.value,
    )

    try:
        db.add(contact)
        await db.commit()
        await db.refresh(contact)
    except IntegrityError:
        await db.rollback()
        raise HTTPException(
            status_code=409,
            detail=f"Contact with email '{request.email}' already exists for this client",
        )

    logger.info(
        "Contact created",
        extra={
            "contact_id": str(contact.id),
            "email": contact.email,
            "user_id": str(auth.user.id) if auth.user.id else None,
        },
    )

    return ContactResponse(
        id=contact.id,
        client_id=contact.client_id,
        email=contact.email,
        first_name=contact.first_name,
        last_name=contact.last_name,
        full_name=contact.full_name,
        status=contact.status,
        source=contact.source,
        custom_fields=contact.custom_fields,
        created_at=contact.created_at,
        updated_at=contact.updated_at,
        groups=None,
    )


@router.post("/bulk", response_model=BulkContactResponse, status_code=201)
async def bulk_create_contacts(
    request: BulkContactCreate,
    client_id: str | None = Query(
        default=None, description="Administrators only: client the contacts are created for"
    ),
    db: AsyncSession = Depends(get_db),
    auth: AuthContext = Depends(require_scopes("mailler:write")),
) -> BulkContactResponse:
    """Create multiple contacts at once.

    Args:
        request: List of contacts to create
        db: Database session
        auth: Authentication context

    Returns:
        Bulk operation result
    """
    owner = auth.target_client_id(client_id)
    created = 0
    skipped = 0
    failed = 0
    errors = []

    for contact_data in request.contacts:
        try:
            # Check if contact already exists
            existing = await db.execute(
                select(Contact).where(
                    Contact.client_id == owner, Contact.email == contact_data.email
                )
            )
            if existing.scalar_one_or_none():
                if request.skip_existing:
                    skipped += 1
                    continue
                else:
                    failed += 1
                    errors.append(f"Email '{contact_data.email}' already exists")
                    continue

            contact = Contact(
                client_id=owner,
                email=contact_data.email,
                first_name=contact_data.first_name,
                last_name=contact_data.last_name,
                source=contact_data.source,
                custom_fields=contact_data.custom_fields or {},
                status=ContactStatus.ACTIVE.value,
            )
            db.add(contact)
            created += 1

        except Exception as e:
            failed += 1
            errors.append(f"Failed to create '{contact_data.email}': {str(e)}")

    await db.commit()

    logger.info(
        "Bulk contacts created",
        extra={
            "created_count": created,
            "skipped_count": skipped,
            "failed_count": failed,
            "user_id": str(auth.user.id) if auth.user.id else None,
        },
    )

    return BulkContactResponse(
        created=created,
        skipped=skipped,
        failed=failed,
        errors=errors if errors else None,
    )


@router.get("/{contact_id}", response_model=ContactResponse)
async def get_contact(
    contact_id: UUID,
    db: AsyncSession = Depends(get_db),
    auth: AuthContext = Depends(require_scopes("mailler:read")),
) -> ContactResponse:
    """Get contact by ID.

    A contact of another client is reported as not found.

    Args:
        contact_id: Contact UUID
        db: Database session
        auth: Authentication context

    Returns:
        Contact details

    Raises:
        HTTPException: If contact not found
    """
    # Load contact with group memberships and groups eagerly
    stmt = (
        select(Contact)
        .where(Contact.id == contact_id)
        .options(selectinload(Contact.group_memberships).selectinload(ContactGroupMember.group))
    )
    result = await db.execute(stmt)
    contact = result.scalar_one_or_none()
    if not contact or not auth.owns(contact.client_id):
        raise HTTPException(status_code=404, detail="Contact not found")

    # Get groups for this contact
    from mailler.schemas.contact import ContactGroupBasic

    groups = [
        ContactGroupBasic(id=m.group.id, slug=m.group.slug, name=m.group.name)
        for m in contact.group_memberships
        if m.group
    ]

    return ContactResponse(
        id=contact.id,
        client_id=contact.client_id,
        email=contact.email,
        first_name=contact.first_name,
        last_name=contact.last_name,
        full_name=contact.full_name,
        status=contact.status,
        source=contact.source,
        custom_fields=contact.custom_fields,
        created_at=contact.created_at,
        updated_at=contact.updated_at,
        groups=groups,
    )


@router.get("/by-email/{email}", response_model=ContactResponse)
async def get_contact_by_email(
    email: str,
    client_id: str | None = Query(
        default=None, description="Administrators only: client owning the contact"
    ),
    db: AsyncSession = Depends(get_db),
    auth: AuthContext = Depends(require_scopes("mailler:read")),
) -> ContactResponse:
    """Get a contact of the calling client by email address.

    The same address can be a contact of several clients, so the lookup is
    always made inside one client: the caller's own, or the one an
    administrator names.

    Args:
        email: Contact email
        client_id: Client owning the contact, administrators only
        db: Database session
        auth: Authentication context

    Returns:
        Contact details

    Raises:
        HTTPException: If contact not found
    """
    stmt = (
        select(Contact)
        .where(Contact.client_id == auth.target_client_id(client_id), Contact.email == email)
        .options(selectinload(Contact.group_memberships).selectinload(ContactGroupMember.group))
    )
    result = await db.execute(stmt)
    contact = result.scalar_one_or_none()

    if not contact:
        raise HTTPException(status_code=404, detail="Contact not found")

    # Get groups for this contact
    from mailler.schemas.contact import ContactGroupBasic

    groups = [
        ContactGroupBasic(id=m.group.id, slug=m.group.slug, name=m.group.name)
        for m in contact.group_memberships
        if m.group
    ]

    return ContactResponse(
        id=contact.id,
        client_id=contact.client_id,
        email=contact.email,
        first_name=contact.first_name,
        last_name=contact.last_name,
        full_name=contact.full_name,
        status=contact.status,
        source=contact.source,
        custom_fields=contact.custom_fields,
        created_at=contact.created_at,
        updated_at=contact.updated_at,
        groups=groups,
    )


@router.put("/{contact_id}", response_model=ContactResponse)
async def update_contact(
    contact_id: UUID,
    request: ContactUpdate,
    db: AsyncSession = Depends(get_db),
    auth: AuthContext = Depends(require_scopes("mailler:write")),
) -> ContactResponse:
    """Update a contact.

    Args:
        contact_id: Contact UUID
        request: Updated contact data
        db: Database session
        auth: Authentication context

    Returns:
        Updated contact

    Raises:
        HTTPException: If contact not found
    """
    contact = await db.get(Contact, contact_id)
    if not contact or not auth.owns(contact.client_id):
        raise HTTPException(status_code=404, detail="Contact not found")

    # Track if we need to unblock in Brevo
    old_status = contact.status
    needs_brevo_unblock = False

    # Update fields if provided
    if request.first_name is not None:
        contact.first_name = request.first_name
    if request.last_name is not None:
        contact.last_name = request.last_name
    if request.status is not None:
        # Check if status is changing from bounced/complained to active
        if (
            old_status in [ContactStatus.BOUNCED.value, ContactStatus.COMPLAINED.value]
            and request.status == ContactStatus.ACTIVE.value
        ):
            needs_brevo_unblock = True
        contact.status = request.status
    if request.source is not None:
        contact.source = request.source
    if request.custom_fields is not None:
        contact.custom_fields = request.custom_fields

    # Unblock in Brevo if status changed from bounced/complained to active
    if needs_brevo_unblock:
        from mailler.services.providers.brevo import BrevoProvider

        brevo = BrevoProvider()
        if brevo.is_configured:
            unblock_result = await brevo.unblock_contact(contact.email)
            if unblock_result.get("success"):
                logger.info(
                    "Contact unblocked in Brevo",
                    extra={
                        "contact_id": str(contact.id),
                        "email": contact.email,
                        "brevo_message": unblock_result.get("message"),
                    },
                )
            else:
                logger.warning(
                    "Failed to unblock contact in Brevo",
                    extra={
                        "contact_id": str(contact.id),
                        "email": contact.email,
                        "error": unblock_result.get("error"),
                    },
                )

    await db.commit()

    logger.info(
        "Contact updated",
        extra={
            "contact_id": str(contact.id),
            "email": contact.email,
            "user_id": str(auth.user.id) if auth.user.id else None,
        },
    )

    # Reload contact with relationships for response
    stmt = (
        select(Contact)
        .where(Contact.id == contact_id)
        .options(selectinload(Contact.group_memberships).selectinload(ContactGroupMember.group))
    )
    result = await db.execute(stmt)
    contact = result.scalar_one()

    # Get groups for this contact
    from mailler.schemas.contact import ContactGroupBasic

    groups = [
        ContactGroupBasic(id=m.group.id, slug=m.group.slug, name=m.group.name)
        for m in contact.group_memberships
        if m.group
    ]

    return ContactResponse(
        id=contact.id,
        client_id=contact.client_id,
        email=contact.email,
        first_name=contact.first_name,
        last_name=contact.last_name,
        full_name=contact.full_name,
        status=contact.status,
        source=contact.source,
        custom_fields=contact.custom_fields,
        created_at=contact.created_at,
        updated_at=contact.updated_at,
        groups=groups,
    )


@router.delete("/{contact_id}", status_code=204)
async def delete_contact(
    contact_id: UUID,
    db: AsyncSession = Depends(get_db),
    auth: AuthContext = Depends(require_scopes("mailler:write")),
) -> None:
    """Delete a contact.

    Args:
        contact_id: Contact UUID
        db: Database session
        auth: Authentication context

    Raises:
        HTTPException: If contact not found
    """
    contact = await db.get(Contact, contact_id)
    if not contact or not auth.owns(contact.client_id):
        raise HTTPException(status_code=404, detail="Contact not found")

    logger.info(
        "Contact deleted",
        extra={
            "contact_id": str(contact.id),
            "email": contact.email,
            "user_id": str(auth.user.id) if auth.user.id else None,
        },
    )

    await db.delete(contact)
    await db.commit()


@router.post("/{contact_id}/unsubscribe", response_model=ContactResponse)
async def unsubscribe_contact(
    contact_id: UUID,
    db: AsyncSession = Depends(get_db),
    auth: AuthContext = Depends(require_scopes("mailler:write")),
) -> ContactResponse:
    """Unsubscribe a contact from all emails.

    Args:
        contact_id: Contact UUID
        db: Database session
        auth: Authentication context

    Returns:
        Updated contact

    Raises:
        HTTPException: If contact not found
    """
    contact = await db.get(Contact, contact_id)
    if not contact or not auth.owns(contact.client_id):
        raise HTTPException(status_code=404, detail="Contact not found")

    contact.status = ContactStatus.UNSUBSCRIBED.value
    await db.commit()
    await db.refresh(contact)

    logger.info(
        "Contact unsubscribed",
        extra={
            "contact_id": str(contact.id),
            "email": contact.email,
            "user_id": str(auth.user.id) if auth.user.id else None,
        },
    )

    return ContactResponse(
        id=contact.id,
        client_id=contact.client_id,
        email=contact.email,
        first_name=contact.first_name,
        last_name=contact.last_name,
        full_name=contact.full_name,
        status=contact.status,
        source=contact.source,
        custom_fields=contact.custom_fields,
        created_at=contact.created_at,
        updated_at=contact.updated_at,
        groups=None,
    )
