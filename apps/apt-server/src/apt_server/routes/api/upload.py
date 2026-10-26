# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Chunked upload API endpoints."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from apt_server.acl import scopes as scope_rules
from apt_server.acl.packages import Caller
from apt_server.database import get_db
from apt_server.db.models import PackageVisibility
from apt_server.routes.api.packages import PackageRead
from apt_server.services.apt_auth import Caller_
from apt_server.services.chunked_upload import (
    assemble,
    create_session,
    delete_session,
    get_manifest,
    save_chunk,
)
from apt_server.services.upload import UploadConflictError, UploadValidationError, save_upload

router = APIRouter(prefix="/upload", tags=["upload"])


def _require_caller(caller: Caller | None) -> Caller:
    if caller is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="authentication required"
        )
    return caller


class InitRequest(BaseModel):
    filename: str
    total_size: int
    total_chunks: int
    suite: str
    component: str
    visibility: str = "private"


class InitResponse(BaseModel):
    upload_id: str
    chunk_size: int


class ChunkResponse(BaseModel):
    upload_id: str
    index: int
    received: int
    total: int


@router.post("/init", response_model=InitResponse)
async def init_upload(caller: Caller_, payload: InitRequest) -> InitResponse:
    """Create a chunked upload session."""
    user = _require_caller(caller)
    # Session users (web UI) are already interactively authenticated — ownership
    # enforcement is sufficient. Scope checks only apply to PAT/API callers.
    if not user.is_session and not scope_rules.may_write(set(user.scopes), payload.component):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="insufficient scope")

    try:
        upload_id = create_session(
            filename=payload.filename,
            total_size=payload.total_size,
            total_chunks=payload.total_chunks,
            owner_id=user.sub,
            suite=payload.suite,
            component=payload.component,
            visibility=payload.visibility,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))

    from apt_server.config import settings

    return InitResponse(upload_id=upload_id, chunk_size=settings.upload_chunk_size)


@router.post("/{upload_id}/chunk", response_model=ChunkResponse)
async def upload_chunk(
    caller: Caller_,
    upload_id: str,
    chunk: UploadFile,
    index: Annotated[int, Query(ge=0)],
) -> ChunkResponse:
    """Upload a single chunk."""
    user = _require_caller(caller)
    try:
        manifest = get_manifest(upload_id)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="session not found")

    if manifest["owner_id"] != user.sub:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="not your upload")

    data = await chunk.read()
    try:
        manifest = save_chunk(upload_id, index, data)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))

    return ChunkResponse(
        upload_id=upload_id,
        index=index,
        received=len(manifest["received_chunks"]),
        total=manifest["total_chunks"],
    )


@router.post("/{upload_id}/complete", response_model=PackageRead)
async def complete_upload(
    caller: Caller_,
    db: Annotated[AsyncSession, Depends(get_db)],
    upload_id: str,
) -> PackageRead:
    """Assemble chunks and finalize the package."""
    user = _require_caller(caller)
    try:
        manifest = get_manifest(upload_id)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="session not found")

    if manifest["owner_id"] != user.sub:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="not your upload")

    try:
        assembled, _ = assemble(upload_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))

    raw = assembled.read_bytes()
    vis = manifest.get("visibility", "private")
    visibility = (
        PackageVisibility(vis)
        if vis in ("public", "private", "shared")
        else PackageVisibility.PRIVATE
    )

    try:
        package = await save_upload(
            db,
            caller=user,
            suite=manifest["suite"],
            component=manifest["component"],
            raw_body=raw,
            visibility=visibility,
        )
    except UploadValidationError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    except UploadConflictError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"package already exists: {exc.existing.id}",
        )
    finally:
        delete_session(upload_id)

    return PackageRead.from_row(package)


@router.delete("/{upload_id}", status_code=status.HTTP_204_NO_CONTENT)
async def cancel_upload(caller: Caller_, upload_id: str) -> None:
    """Cancel and clean up an in-progress upload."""
    user = _require_caller(caller)
    try:
        manifest = get_manifest(upload_id)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="session not found")

    if manifest["owner_id"] != user.sub:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="not your upload")

    delete_session(upload_id)
