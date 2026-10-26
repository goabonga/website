# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Admin endpoint to flush the per-caller ``Packages`` cache."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from apt_server.acl import scopes as scope_rules
from apt_server.auth.dependencies import Auth
from apt_server.database import get_db
from apt_server.db.models import IndexCache
from apt_server.services.caller import caller_from_auth

router = APIRouter(prefix="/reindex", tags=["admin"])


@router.post("", status_code=status.HTTP_204_NO_CONTENT)
async def reindex(
    auth: Auth,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> None:
    """Drop every cached ``Packages`` rendering.

    The next ``apt update`` will re-render from the database. This is
    normally unnecessary — uploads and deletes already invalidate cached
    entries — but it is kept as an escape hatch after an out-of-band
    change to the repository (GPG key rotation, manual pool surgery).
    Requires ``apt:admin``.
    """
    caller = caller_from_auth(auth)
    if not scope_rules.may_reindex(set(caller.scopes)):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Missing required scope: apt:admin",
        )
    await db.execute(delete(IndexCache))
    await db.commit()
