# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Content of an email sent from a template.

A request carries either the content of the email or the slug of a template of
its client; in the second case the subject, the HTML and the plain text are
rendered here, on the server, from the variables of the request.
"""

from dataclasses import dataclass, field

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from mailler.auth import AuthContext
from mailler.models.template import EmailTemplate, TemplateStatus
from mailler.schemas.email import SendEmailRequest
from mailler.services.mjml import html_to_plain_text
from mailler.services.rendering import RenderError, render_parts

# Length of the subject column
SUBJECT_MAX_LENGTH = 500


@dataclass(frozen=True)
class EmailContent:
    """What goes in an email, whether it was given or rendered."""

    subject: str
    html: str
    text: str | None
    metadata: dict = field(default_factory=dict)
    missing_variables: list[str] = field(default_factory=list)


async def resolve_content(
    db: AsyncSession, auth: AuthContext, request: SendEmailRequest
) -> EmailContent:
    """Return the content of the email of a request, rendering its template if it has one.

    The template is looked up among the templates of the caller's client (an
    administrator uses its own client), so a client can only send its own.

    Raises:
        HTTPException: 404 when the template does not exist, 422 when it cannot
            be used (not active, not compiled) or its rendering fails.
    """
    metadata = dict(request.metadata or {})
    if not request.template_slug:
        return EmailContent(
            subject=request.subject or "",
            html=request.html_content or "",
            text=request.text_content,
            metadata=metadata,
        )

    result = await db.execute(
        select(EmailTemplate).where(
            EmailTemplate.client_id == auth.target_client_id(),
            EmailTemplate.slug == request.template_slug,
        )
    )
    template = result.scalar_one_or_none()
    if template is None:
        raise HTTPException(status_code=404, detail=f"Template '{request.template_slug}' not found")
    if template.status != TemplateStatus.ACTIVE.value:
        raise HTTPException(
            status_code=422, detail=f"Template '{request.template_slug}' is not active"
        )
    if not template.html_compiled:
        raise HTTPException(
            status_code=422, detail=f"Template '{request.template_slug}' has not been compiled"
        )

    variables = request.variables or {}
    try:
        rendered = render_parts(
            subject_template=template.subject_template,
            html_compiled=template.html_compiled,
            plain_text=template.plain_text,
            variables=variables,
        )
    except RenderError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error

    subject = rendered.subject.strip()
    if not subject:
        raise HTTPException(status_code=422, detail="The rendered subject is empty")
    if len(subject) > SUBJECT_MAX_LENGTH:
        raise HTTPException(
            status_code=422,
            detail=f"The rendered subject is longer than {SUBJECT_MAX_LENGTH} characters",
        )

    metadata["template_slug"] = template.slug
    return EmailContent(
        subject=subject,
        html=rendered.html,
        text=rendered.plain_text or html_to_plain_text(rendered.html) or None,
        metadata=metadata,
        missing_variables=[name for name in (template.variables or []) if name not in variables],
    )
