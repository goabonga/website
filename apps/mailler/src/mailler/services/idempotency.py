# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Idempotency of the sending requests.

A client that is not sure a request reached the service (a timeout, a retry
after a crash) repeats it with the same ``Idempotency-Key`` header: the first
email is returned again instead of a second one being sent.
"""

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from mailler.models.email import Email
from mailler.schemas.email import SendEmailResponse

HEADER = "Idempotency-Key"
MAX_LENGTH = 255


async def find_replay(
    db: AsyncSession, client_id: str | None, key: str | None, to_email: str
) -> Email | None:
    """Return the email already created for this key of this client, or None.

    Raises:
        HTTPException: 422 when the key was used for an email to another recipient.
    """
    if not key:
        return None
    condition = Email.client_id == client_id if client_id else Email.client_id.is_(None)
    result = await db.execute(select(Email).where(condition, Email.idempotency_key == key))
    existing = result.scalar_one_or_none()
    if existing is None:
        return None
    if existing.to_email.lower() != to_email.lower():
        raise HTTPException(
            status_code=422, detail=f"{HEADER} was already used for another request"
        )
    return existing


def replay_response(email: Email) -> SendEmailResponse:
    """The response of a request that was already processed."""
    return SendEmailResponse(
        id=str(email.id),
        status="scheduled" if email.scheduled_at else "queued",
        message=f"Already submitted with this {HEADER}",
        task_id=email.task_id,
    )
