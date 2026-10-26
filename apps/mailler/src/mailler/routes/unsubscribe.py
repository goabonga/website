# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Public unsubscribe routes.

These routes are PUBLIC (no authentication required) and allow email
recipients to unsubscribe using a signed URL.
"""

from urllib.parse import quote

from fastapi import APIRouter, Depends, Query
from fastapi.responses import HTMLResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from mailler.database import get_db
from mailler.logging import get_logger
from mailler.models.contact import Contact, ContactStatus
from mailler.services.webhook_signature import verify_unsubscribe_signature

logger = get_logger(__name__)

router = APIRouter(tags=["Unsubscribe"])


# HTML templates for the unsubscribe pages
UNSUBSCRIBE_CONFIRM_HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Unsubscribe</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: linear-gradient(135deg, #0f0f23 0%, #1a1a2e 100%);
            min-height: 100vh;
            display: flex;
            align-items: center;
            justify-content: center;
            color: #ffffff;
        }}
        .container {{
            background: #16213e;
            padding: 2.5rem;
            border-radius: 12px;
            box-shadow: 0 4px 20px rgba(0,0,0,0.3);
            max-width: 450px;
            text-align: center;
        }}
        h1 {{ font-size: 1.5rem; margin-bottom: 1rem; }}
        p {{ color: #a0a0a0; margin-bottom: 1.5rem; line-height: 1.6; }}
        .email {{ color: #e94560; font-weight: 600; }}
        form {{ display: flex; gap: 1rem; justify-content: center; flex-wrap: wrap; }}
        button {{
            padding: 0.75rem 1.5rem;
            border: none;
            border-radius: 6px;
            font-size: 1rem;
            cursor: pointer;
            transition: transform 0.2s, box-shadow 0.2s;
        }}
        button:hover {{ transform: translateY(-2px); }}
        .btn-danger {{
            background: #e94560;
            color: white;
        }}
        .btn-danger:hover {{ box-shadow: 0 4px 12px rgba(233, 69, 96, 0.4); }}
        .btn-secondary {{
            background: #2a2a4a;
            color: #a0a0a0;
        }}
        .btn-secondary:hover {{ background: #3a3a5a; }}
    </style>
</head>
<body>
    <div class="container">
        <h1>Unsubscribe from emails</h1>
        <p>
            Are you sure you want to unsubscribe<br>
            <span class="email">{email}</span><br>
            from all future emails?
        </p>
        <form method="POST" action="/api/v1/unsubscribe?email={email_query}&amp;client={client_query}&amp;sig={sig_query}">
            <button type="submit" class="btn-danger">Yes, unsubscribe me</button>
            <button type="button" class="btn-secondary" onclick="window.close()">Cancel</button>
        </form>
    </div>
</body>
</html>
"""

UNSUBSCRIBE_SUCCESS_HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Unsubscribed</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: linear-gradient(135deg, #0f0f23 0%, #1a1a2e 100%);
            min-height: 100vh;
            display: flex;
            align-items: center;
            justify-content: center;
            color: #ffffff;
        }}
        .container {{
            background: #16213e;
            padding: 2.5rem;
            border-radius: 12px;
            box-shadow: 0 4px 20px rgba(0,0,0,0.3);
            max-width: 450px;
            text-align: center;
        }}
        .icon {{ font-size: 3rem; margin-bottom: 1rem; }}
        h1 {{ font-size: 1.5rem; margin-bottom: 1rem; color: #00b894; }}
        p {{ color: #a0a0a0; line-height: 1.6; }}
        .email {{ color: #e94560; font-weight: 600; }}
    </style>
</head>
<body>
    <div class="container">
        <div class="icon">&#10003;</div>
        <h1>Successfully unsubscribed</h1>
        <p>
            <span class="email">{email}</span><br>
            has been removed from our mailing list.<br>
            You will no longer receive emails from us.
        </p>
    </div>
</body>
</html>
"""

UNSUBSCRIBE_ERROR_HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Unsubscribe Error</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: linear-gradient(135deg, #0f0f23 0%, #1a1a2e 100%);
            min-height: 100vh;
            display: flex;
            align-items: center;
            justify-content: center;
            color: #ffffff;
        }}
        .container {{
            background: #16213e;
            padding: 2.5rem;
            border-radius: 12px;
            box-shadow: 0 4px 20px rgba(0,0,0,0.3);
            max-width: 450px;
            text-align: center;
        }}
        .icon {{ font-size: 3rem; margin-bottom: 1rem; }}
        h1 {{ font-size: 1.5rem; margin-bottom: 1rem; color: #e94560; }}
        p {{ color: #a0a0a0; line-height: 1.6; }}
    </style>
</head>
<body>
    <div class="container">
        <div class="icon">&#10060;</div>
        <h1>Unsubscribe failed</h1>
        <p>{message}</p>
    </div>
</body>
</html>
"""


@router.get("/unsubscribe", response_class=HTMLResponse)
async def unsubscribe_confirm(
    email: str = Query(..., description="Email address to unsubscribe"),
    client: str = Query(..., description="Client the contact belongs to"),
    sig: str = Query(..., description="Signature for verification"),
) -> HTMLResponse:
    """Display unsubscribe confirmation page.

    This is a PUBLIC endpoint (no authentication required).
    The signature ensures that only the recipient can unsubscribe.
    """
    # Verify signature
    if not verify_unsubscribe_signature(email, client, sig):
        logger.warning(
            "Invalid unsubscribe signature",
            extra={"email": email, "client_id": client},
        )
        return HTMLResponse(
            content=UNSUBSCRIBE_ERROR_HTML.format(
                message="Invalid or expired unsubscribe link.<br>Please use the link from your email."
            ),
            status_code=403,
        )

    return HTMLResponse(
        content=UNSUBSCRIBE_CONFIRM_HTML.format(
            email=email,
            email_query=quote(email, safe=""),
            client_query=quote(client, safe=""),
            sig_query=quote(sig, safe=""),
        ),
        status_code=200,
    )


@router.post("/unsubscribe", response_class=HTMLResponse)
async def unsubscribe_process(
    email: str = Query(..., description="Email address to unsubscribe"),
    client: str = Query(..., description="Client the contact belongs to"),
    sig: str = Query(..., description="Signature for verification"),
    db: AsyncSession = Depends(get_db),
) -> HTMLResponse:
    """Process unsubscribe request.

    This is a PUBLIC endpoint (no authentication required).
    The signature ensures that only the recipient can unsubscribe.
    """
    # Verify signature
    if not verify_unsubscribe_signature(email, client, sig):
        logger.warning(
            "Invalid unsubscribe signature on POST",
            extra={"email": email, "client_id": client},
        )
        return HTMLResponse(
            content=UNSUBSCRIBE_ERROR_HTML.format(
                message="Invalid or expired unsubscribe link.<br>Please use the link from your email."
            ),
            status_code=403,
        )

    # Find the contact of that client by email: the same address can be a contact of
    # several clients and only the one that sent the email is unsubscribed
    stmt = select(Contact).where(Contact.client_id == client, Contact.email == email.lower())
    result = await db.execute(stmt)
    contact = result.scalar_one_or_none()

    if not contact:
        logger.warning(
            "Unsubscribe for unknown contact",
            extra={"email": email},
        )
        # Still show success to avoid email enumeration
        return HTMLResponse(
            content=UNSUBSCRIBE_SUCCESS_HTML.format(email=email),
            status_code=200,
        )

    # Check if already unsubscribed
    if contact.status == ContactStatus.UNSUBSCRIBED.value:
        logger.info(
            "Contact already unsubscribed",
            extra={"email": email, "contact_id": str(contact.id)},
        )
        return HTMLResponse(
            content=UNSUBSCRIBE_SUCCESS_HTML.format(email=email),
            status_code=200,
        )

    # Update contact status
    contact.status = ContactStatus.UNSUBSCRIBED.value
    await db.commit()

    logger.info(
        "Contact unsubscribed via link",
        extra={"email": email, "contact_id": str(contact.id)},
    )

    return HTMLResponse(
        content=UNSUBSCRIBE_SUCCESS_HTML.format(email=email),
        status_code=200,
    )
