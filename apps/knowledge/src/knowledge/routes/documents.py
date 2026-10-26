# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Document routes."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from knowledge.auth.dependencies import Auth
from knowledge.database import get_db
from knowledge.schemas.document import (
    DocumentCreate,
    DocumentResponse,
    DocumentsCreate,
)
from knowledge.services.collections import CollectionService
from knowledge.services.documents import DocumentService

router = APIRouter(tags=["Documents"])


async def get_collection_or_404(
    collection_id: str,
    auth: Auth,
    db: AsyncSession,
):
    """Get collection or raise 404."""
    service = CollectionService(db)
    collection = await service.get_by_id_or_slug(auth.tenant_id, collection_id)
    if not collection:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Collection not found",
        )
    return collection


@router.post(
    "/collections/{collection_id}/documents",
    response_model=list[DocumentResponse],
    status_code=status.HTTP_201_CREATED,
)
async def add_documents(
    collection_id: str,
    data: DocumentsCreate,
    auth: Auth,
    db: AsyncSession = Depends(get_db),
) -> list[DocumentResponse]:
    """Add documents to a collection."""
    auth.require_scope("documents:write")

    collection = await get_collection_or_404(collection_id, auth, db)

    service = DocumentService(db)
    documents = await service.create_batch(collection.id, data.documents)

    return [DocumentResponse.model_validate(doc) for doc in documents]


@router.post(
    "/collections/{collection_id}/documents/single",
    response_model=DocumentResponse,
    status_code=status.HTTP_201_CREATED,
)
async def add_document(
    collection_id: str,
    data: DocumentCreate,
    auth: Auth,
    db: AsyncSession = Depends(get_db),
) -> DocumentResponse:
    """Add a single document to a collection."""
    auth.require_scope("documents:write")

    collection = await get_collection_or_404(collection_id, auth, db)

    service = DocumentService(db)
    document = await service.create(collection.id, data)

    return DocumentResponse.model_validate(document)


@router.get(
    "/collections/{collection_id}/documents",
    response_model=list[DocumentResponse],
)
async def list_documents(
    collection_id: str,
    auth: Auth,
    db: AsyncSession = Depends(get_db),
    offset: int = 0,
    limit: int = 100,
) -> list[DocumentResponse]:
    """List documents in a collection."""
    auth.require_scope("documents:read")

    collection = await get_collection_or_404(collection_id, auth, db)

    service = DocumentService(db)
    documents = await service.list(collection.id, offset, limit)

    return [DocumentResponse.model_validate(doc) for doc in documents]


@router.get("/documents/{document_id}", response_model=DocumentResponse)
async def get_document(
    document_id: UUID,
    auth: Auth,
    db: AsyncSession = Depends(get_db),
) -> DocumentResponse:
    """Get a document by ID."""
    auth.require_scope("documents:read")

    service = DocumentService(db)
    document = await service.get_by_id(document_id)

    if not document:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found",
        )

    # Verify tenant owns this document via collection
    collection_service = CollectionService(db)
    collection = await collection_service.get_by_id(auth.tenant_id, document.collection_id)
    if not collection:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found",
        )

    return DocumentResponse.model_validate(document)


@router.delete(
    "/collections/{collection_id}/documents/{document_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_document(
    collection_id: str,
    document_id: UUID,
    auth: Auth,
    db: AsyncSession = Depends(get_db),
) -> None:
    """Delete a document."""
    auth.require_scope("documents:write")

    collection = await get_collection_or_404(collection_id, auth, db)

    service = DocumentService(db)
    deleted = await service.delete(document_id, collection.id)

    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found",
        )
