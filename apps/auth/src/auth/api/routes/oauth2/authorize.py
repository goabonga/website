# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""OAuth2 authorization endpoint."""

import logging
from urllib.parse import urlencode, urlparse

from fastapi import APIRouter, Depends, Form, HTTPException, Query, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from auth.api.deps import (
    get_branding_service,
    get_db,
    get_jar_service,
    get_oauth2_client_service,
    get_par_service,
    get_session_service,
)
from auth.api.schemas.oauth2 import OAuth2Error
from auth.middlewares.tenant import get_session_cookie_name, get_tenant_context
from auth.services.branding import BrandingService
from auth.services.issuer import get_issuer_from_context
from auth.services.jar import JARError, JARService
from auth.services.oauth2_client import OAuth2ClientService
from auth.services.par import PAR_REQUEST_URI_PREFIX, PARService
from auth.services.pkce import is_valid_code_challenge, is_valid_code_challenge_method
from auth.services.session import SessionService

logger = logging.getLogger(__name__)

router = APIRouter()


def get_tenant_prefix() -> str:
    """Get the URL prefix for the current tenant if resolved via path.

    Returns:
        The tenant prefix (e.g., '/t/knowledge') if using path resolution,
        or empty string otherwise.
    """
    tenant_ctx = get_tenant_context()
    if tenant_ctx and tenant_ctx.tenant_slug and tenant_ctx.resolution_method == "path":
        return f"/t/{tenant_ctx.tenant_slug}"
    return ""


def get_current_tenant_id():
    """Get the current tenant ID from context."""
    tenant_ctx = get_tenant_context()
    return tenant_ctx.tenant_id if tenant_ctx else None


async def render_oauth2_error(
    db: AsyncSession,
    branding_service: BrandingService,
    request: Request,
    error: str,
    error_description: str,
    status_code: int = status.HTTP_400_BAD_REQUEST,
) -> HTMLResponse:
    """Render an OAuth2 error page with tenant branding."""
    tenant_id = get_current_tenant_id()
    html = await branding_service.render_template(
        db,
        "oauth2/error.html",
        {"request": request, "error": error, "error_description": error_description},
        tenant_id=tenant_id,
    )
    return HTMLResponse(content=html, status_code=status_code)


def _get_external_url(request: Request) -> str:
    """Get the external URL respecting proxy headers (X-Forwarded-Proto, X-Forwarded-Host).

    Also restores the tenant path prefix (/t/{slug}) that the TenantMiddleware
    strips from scope["path"] during path-based tenant resolution.
    """
    scheme = request.headers.get("x-forwarded-proto", request.url.scheme)
    host = request.headers.get("x-forwarded-host", request.headers.get("host", request.url.netloc))
    tenant_prefix = get_tenant_prefix()
    path = f"{tenant_prefix}{request.url.path}"
    return (
        f"{scheme}://{host}{path}?{request.url.query}"
        if request.url.query
        else f"{scheme}://{host}{path}"
    )


def _build_error_redirect(
    redirect_uri: str,
    error: str,
    error_description: str | None = None,
    state: str | None = None,
) -> str:
    """Build an error redirect URL."""
    params = {"error": error}
    if error_description:
        params["error_description"] = error_description
    if state:
        params["state"] = state

    separator = "&" if "?" in redirect_uri else "?"
    return f"{redirect_uri}{separator}{urlencode(params)}"


def _build_success_redirect(
    redirect_uri: str,
    code: str,
    state: str | None = None,
) -> str:
    """Build a success redirect URL with authorization code."""
    params = {"code": code}
    if state:
        params["state"] = state

    separator = "&" if "?" in redirect_uri else "?"
    return f"{redirect_uri}{separator}{urlencode(params)}"


def _parse_scopes(scope: str | None) -> list[str]:
    """Parse space-separated scopes into a list."""
    if not scope:
        return ["openid"]
    return scope.split()


def _is_valid_redirect_uri(uri: str) -> bool:
    """Basic validation of redirect URI.

    Supports:
    - https:// - always allowed
    - http:// - only for localhost (127.0.0.1, [::1], localhost)
    - Custom schemes (e.g., vpnclient://) - for native app deep links
    """
    try:
        parsed = urlparse(uri)
        # Must have a scheme
        if not parsed.scheme:
            return False

        # Standard HTTP(S) validation
        if parsed.scheme in ("http", "https"):
            # Must have netloc for http/https
            if not parsed.netloc:
                return False
            # Allow http for localhost only
            return not (
                parsed.scheme == "http"
                and parsed.netloc
                not in (
                    "localhost",
                    "127.0.0.1",
                    "[::1]",
                )
                and not parsed.netloc.startswith("localhost:")
                and not parsed.netloc.startswith("127.0.0.1:")
            )

        # Custom scheme validation (for native apps like vpnclient://)
        # Must have a valid scheme name (letters, digits, +, -, .)
        # RFC 3986: scheme = ALPHA *( ALPHA / DIGIT / "+" / "-" / "." )
        # Defence in depth: urlparse already refuses to populate ``scheme``
        # unless it matches this grammar, so these guards cannot fire today —
        # they exist in case the parser is ever swapped out.
        if not parsed.scheme[0].isalpha():  # pragma: no cover
            return False
        for char in parsed.scheme[1:]:  # pragma: no cover
            if not (char.isalnum() or char in ("+", "-", ".")):
                return False

        # Custom schemes must have a path or netloc
        return bool(parsed.netloc or parsed.path)
    except Exception:
        return False


@router.get("/authorize", response_model=None)
async def authorize_get(
    request: Request,
    client_id: str = Query(...),
    response_type: str | None = Query(None),
    redirect_uri: str | None = Query(None),
    scope: str | None = Query(None),
    state: str | None = Query(None),
    code_challenge: str | None = Query(None),
    code_challenge_method: str | None = Query(None),
    nonce: str | None = Query(None),
    prompt: str | None = Query(None),
    request_uri: str | None = Query(None),
    request_param: str | None = Query(None, alias="request"),
    db: AsyncSession = Depends(get_db),
    session_service: SessionService = Depends(get_session_service),
    oauth2_service: OAuth2ClientService = Depends(get_oauth2_client_service),
    par_service: PARService = Depends(get_par_service),
    jar_service: JARService = Depends(get_jar_service),
    branding_service: BrandingService = Depends(get_branding_service),
) -> HTMLResponse | RedirectResponse:
    """Initiate the OAuth2 authorization code flow.

    This is the Authorization Endpoint defined by RFC 6749 §3.1. The
    user-agent (browser) is directed here by the client application to begin
    an authorization grant. The server validates `client_id`, `redirect_uri`,
    `response_type=code`, and the requested `scope`. If the user is not
    authenticated their session cookie is absent and they are redirected to
    the login page with the original authorization URL preserved in the `next`
    query parameter. After successful authentication the flow resumes
    automatically.

    If the client has `require_consent=true` the user is shown an interactive
    consent screen (rendered via `oauth2/consent.html`) before a code is
    issued; otherwise the code is issued immediately. On success the server
    redirects to `redirect_uri?code=<code>&state=<state>`. On failure (invalid
    scope, unsupported response type, etc.) it redirects to
    `redirect_uri?error=<code>&error_description=<msg>&state=<state>` per RFC
    6749 §4.1.2.1, except for errors that occur before a trusted `redirect_uri`
    is established (unknown client, missing redirect_uri), which are returned as
    a rendered HTML error page.

    PKCE (RFC 7636) is enforced when the client has `require_pkce=true`.
    `code_challenge` must be a Base64url-encoded SHA-256 hash of the verifier
    and `code_challenge_method` must be `S256` (plain is not supported). If
    `code_challenge_method` is omitted it defaults to `S256`.

    Pushed Authorization Requests (RFC 9126) are supported: pass
    `request_uri=urn:ietf:params:oauth:request_uri:<token>` in place of all
    other parameters to reference a previously submitted PAR object. Each
    `request_uri` is single-use and expires after a short TTL.

    JWT-Secured Authorization Requests (RFC 9101 / JARM) are supported: pass
    the full parameter set as a signed JWT in the `request` query parameter.
    The JWT must be signed with the client's registered key and addressed to
    this authorization server as `aud`.

    OpenID Connect Core §3.1 parameters (`nonce`, `prompt`, `max_age`) are
    honoured when `openid` is included in `scope`. `prompt=login` forces
    re-authentication regardless of existing session.

    **Specification:**
    - RFC 6749 §3.1, §4.1 — Authorization Code Grant
    - RFC 7636 — PKCE (`code_challenge` / `code_challenge_method`)
    - RFC 9126 — Pushed Authorization Requests
    - RFC 9101 — JWT-Secured Authorization Requests (JAR)
    - OpenID Connect Core 1.0 §3.1 — `nonce`, `prompt`, `max_age`

    **Authentication:** session cookie (user must be logged in; redirects to
    `/auth/login?next=<url>` if not)

    **Example:**
    ```
    curl -L \\
      "https://auth.example.com/oauth2/authorize?response_type=code\\
    &client_id=my-app&redirect_uri=https%3A%2F%2Fapp.example.com%2Fcallback\\
    &scope=openid+profile+email\\
    &state=xyzABC123\\
    &code_challenge=E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM\\
    &code_challenge_method=S256\\
    &nonce=n-0S6_WzA2Mj"
    ```
    """
    logger.info("Authorization request: client_id=%s, response_type=%s", client_id, response_type)

    # Get issuer for JAR validation (secure - derived from tenant config, not Host header)
    issuer = await get_issuer_from_context(db)

    # Handle JWT Authorization Request (JAR) - RFC 9101
    if request_param:
        logger.debug("Processing JAR request for client_id=%s", client_id)
        # Get client first for JAR validation
        client = await oauth2_service.get_client_by_client_id(db, client_id)
        if not client or not client.is_active:
            logger.warning("Authorization failed: unknown or inactive client %s", client_id)
            return await render_oauth2_error(
                db,
                branding_service,
                request,
                OAuth2Error.UNAUTHORIZED_CLIENT,
                "Unknown or inactive client",
            )

        # Validate the JWT request object
        try:
            claims = jar_service.validate_request_object(
                request_jwt=request_param,
                client=client,
                expected_issuer=client.client_id,  # JAR issuer should be client_id
                expected_audience=issuer,  # Audience is the authorization server
            )

            # Extract authorization parameters from claims
            jar_params = jar_service.extract_authorization_params(claims, client)

            response_type = jar_params["response_type"]
            redirect_uri = jar_params["redirect_uri"]
            scopes = jar_params["scopes"]
            state = jar_params.get("state")
            code_challenge = jar_params.get("code_challenge")
            code_challenge_method = jar_params.get("code_challenge_method")
            nonce = jar_params.get("nonce")
            prompt = jar_params.get("prompt")

        except JARError as e:
            logger.warning("JAR validation failed: %s - %s", e.error, e.description)
            return await render_oauth2_error(db, branding_service, request, e.error, e.description)

        # Validate response_type from JAR
        if response_type != "code":
            return await render_oauth2_error(
                db,
                branding_service,
                request,
                OAuth2Error.UNSUPPORTED_RESPONSE_TYPE,
                "Only 'code' response type is supported",
            )

        # Validate redirect_uri against client's allowed URIs
        if not oauth2_service.validate_redirect_uri(client, redirect_uri):
            return await render_oauth2_error(
                db,
                branding_service,
                request,
                OAuth2Error.INVALID_REQUEST,
                "redirect_uri not registered for this client",
            )

        # Validate scopes
        if not oauth2_service.validate_scopes(client, scopes):
            return RedirectResponse(
                url=_build_error_redirect(
                    redirect_uri,
                    OAuth2Error.INVALID_SCOPE,
                    "One or more requested scopes are not allowed",
                    state,
                ),
                status_code=status.HTTP_302_FOUND,
            )

        logger.debug("JAR request validated for client_id=%s", client_id)

    # Handle PAR request_uri (RFC 9126)
    elif request_uri:
        logger.debug("Processing PAR request_uri for client_id=%s", client_id)
        # Validate request_uri format
        if not request_uri.startswith(PAR_REQUEST_URI_PREFIX):
            logger.warning("Authorization failed: invalid request_uri format")
            return await render_oauth2_error(
                db,
                branding_service,
                request,
                OAuth2Error.INVALID_REQUEST,
                "Invalid request_uri format",
            )

        # Look up PAR request
        par_request = await par_service.get_par_request_for_client(db, request_uri, client_id)

        if not par_request:
            logger.warning("Authorization failed: unknown or invalid request_uri")
            return await render_oauth2_error(
                db,
                branding_service,
                request,
                OAuth2Error.INVALID_REQUEST,
                "Unknown or invalid request_uri",
            )

        # Check if expired
        if par_service.is_expired(par_request):
            logger.warning("Authorization failed: request_uri has expired")
            return await render_oauth2_error(
                db,
                branding_service,
                request,
                OAuth2Error.INVALID_REQUEST,
                "request_uri has expired",
            )

        # Check if already used
        if par_service.is_used(par_request):
            logger.warning("Authorization failed: request_uri has already been used")
            return await render_oauth2_error(
                db,
                branding_service,
                request,
                OAuth2Error.INVALID_REQUEST,
                "request_uri has already been used",
            )

        # Mark as used (one-time use)
        await par_service.mark_as_used(db, par_request)
        await db.commit()
        logger.debug("PAR request validated and consumed for client_id=%s", client_id)

        # Extract parameters from PAR request
        response_type = par_request.response_type
        redirect_uri = par_request.redirect_uri
        scopes = par_request.scopes
        state = par_request.state
        code_challenge = par_request.code_challenge
        code_challenge_method = par_request.code_challenge_method
        nonce = par_request.nonce
        prompt = par_request.prompt

        # Get client (already validated during PAR)
        client = await oauth2_service.get_client_by_client_id(db, client_id)
        if not client or not client.is_active:
            logger.warning("Authorization failed: unknown or inactive client %s", client_id)
            return await render_oauth2_error(
                db,
                branding_service,
                request,
                OAuth2Error.UNAUTHORIZED_CLIENT,
                "Unknown or inactive client",
            )

    else:
        # Standard authorization request - validate all parameters
        logger.debug("Processing standard authorization request for client_id=%s", client_id)
        if not response_type:
            logger.warning("Authorization failed: response_type is required")
            return await render_oauth2_error(
                db,
                branding_service,
                request,
                OAuth2Error.INVALID_REQUEST,
                "response_type is required",
            )

        if not redirect_uri:
            logger.warning("Authorization failed: redirect_uri is required")
            return await render_oauth2_error(
                db,
                branding_service,
                request,
                OAuth2Error.INVALID_REQUEST,
                "redirect_uri is required",
            )

        # Validate response_type
        if response_type != "code":
            logger.warning("Authorization failed: unsupported response_type %s", response_type)
            return await render_oauth2_error(
                db,
                branding_service,
                request,
                OAuth2Error.UNSUPPORTED_RESPONSE_TYPE,
                "Only 'code' response type is supported",
            )

        # Validate redirect_uri format
        if not _is_valid_redirect_uri(redirect_uri):
            logger.warning("Authorization failed: invalid redirect_uri format")
            return await render_oauth2_error(
                db,
                branding_service,
                request,
                OAuth2Error.INVALID_REQUEST,
                "Invalid redirect_uri",
            )

        # Get client
        client = await oauth2_service.get_client_by_client_id(db, client_id)

        if not client or not client.is_active:
            logger.warning("Authorization failed: unknown or inactive client %s", client_id)
            return await render_oauth2_error(
                db,
                branding_service,
                request,
                OAuth2Error.UNAUTHORIZED_CLIENT,
                "Unknown or inactive client",
            )

        # Validate redirect_uri against client's allowed URIs
        if not oauth2_service.validate_redirect_uri(client, redirect_uri):
            logger.warning(
                "Authorization failed: redirect_uri not registered for client %s", client_id
            )
            return await render_oauth2_error(
                db,
                branding_service,
                request,
                OAuth2Error.INVALID_REQUEST,
                "redirect_uri not registered for this client",
            )

        # Parse and validate scopes
        scopes = _parse_scopes(scope)
        if not oauth2_service.validate_scopes(client, scopes):
            logger.warning("Authorization failed: invalid scope for client %s", client_id)
            return RedirectResponse(
                url=_build_error_redirect(
                    redirect_uri,
                    OAuth2Error.INVALID_SCOPE,
                    "One or more requested scopes are not allowed",
                    state,
                ),
                status_code=status.HTTP_302_FOUND,
            )

        # Validate PKCE
        if client.require_pkce:
            if not code_challenge:
                return RedirectResponse(
                    url=_build_error_redirect(
                        redirect_uri,
                        OAuth2Error.INVALID_REQUEST,
                        "PKCE is required. Provide code_challenge.",
                        state,
                    ),
                    status_code=status.HTTP_302_FOUND,
                )

            # Default to S256 if not specified
            if not code_challenge_method:
                code_challenge_method = "S256"

            if not is_valid_code_challenge_method(code_challenge_method):
                return RedirectResponse(
                    url=_build_error_redirect(
                        redirect_uri,
                        OAuth2Error.INVALID_REQUEST,
                        "Invalid code_challenge_method. Use S256.",
                        state,
                    ),
                    status_code=status.HTTP_302_FOUND,
                )

            if not is_valid_code_challenge(code_challenge):
                return RedirectResponse(
                    url=_build_error_redirect(
                        redirect_uri,
                        OAuth2Error.INVALID_REQUEST,
                        "Invalid code_challenge format",
                        state,
                    ),
                    status_code=status.HTTP_302_FOUND,
                )

    # Check if user is logged in
    session_token = request.cookies.get(get_session_cookie_name())
    user = None

    if session_token:
        user = await session_service.get_user_by_session_token(db, session_token)

    tenant_prefix = get_tenant_prefix()

    # If not logged in, redirect to login
    if not user:
        logger.debug("Authorization: user not authenticated, redirecting to login")
        # Store authorization request in session/query and redirect to login
        login_params = {
            "next": _get_external_url(request),
        }
        login_url = f"{tenant_prefix}/auth/login?{urlencode(login_params)}"
        return RedirectResponse(url=login_url, status_code=status.HTTP_302_FOUND)

    # Check prompt parameter
    if prompt:
        prompts = prompt.split()
        if "login" in prompts:
            logger.debug("Authorization: prompt=login, forcing re-authentication")
            # Force re-authentication
            login_params = {"next": _get_external_url(request)}
            login_url = f"{tenant_prefix}/auth/login?{urlencode(login_params)}"
            return RedirectResponse(url=login_url, status_code=status.HTTP_302_FOUND)

    # If consent is required, show consent page
    if client.require_consent:
        logger.debug("Authorization: showing consent page for client %s", client_id)
        tenant_id = get_current_tenant_id()
        html = await branding_service.render_template(
            db,
            "oauth2/consent.html",
            {
                "request": request,
                "client": client,
                "scopes": scopes,
                "redirect_uri": redirect_uri,
                "state": state,
                "code_challenge": code_challenge,
                "code_challenge_method": code_challenge_method,
                "nonce": nonce,
                "tenant_prefix": tenant_prefix,
            },
            tenant_id=tenant_id,
        )
        return HTMLResponse(content=html)

    # No consent required - generate code directly
    code = await oauth2_service.create_authorization_code(
        db=db,
        client=client,
        user_id=str(user.id),
        redirect_uri=redirect_uri,
        scopes=scopes,
        code_challenge=code_challenge,
        code_challenge_method=code_challenge_method,
        nonce=nonce,
        state=state,
    )

    await db.commit()

    logger.info("Authorization code issued for client %s, user %s", client_id, user.id)
    return RedirectResponse(
        url=_build_success_redirect(redirect_uri, code, state),
        status_code=status.HTTP_302_FOUND,
    )


@router.post("/authorize")
async def authorize_post(
    request: Request,
    consent: str = Form(...),
    client_id: str = Form(...),
    redirect_uri: str = Form(...),
    scope: str | None = Form(None),
    state: str | None = Form(None),
    code_challenge: str | None = Form(None),
    code_challenge_method: str | None = Form(None),
    nonce: str | None = Form(None),
    db: AsyncSession = Depends(get_db),
    session_service: SessionService = Depends(get_session_service),
    oauth2_service: OAuth2ClientService = Depends(get_oauth2_client_service),
) -> RedirectResponse:
    """Submit the OAuth2 consent decision and obtain an authorization code.

    This endpoint receives the HTML form posted by the consent screen
    (`oauth2/consent.html`) after the user explicitly approves or denies the
    authorization request. It is the second step of the Authorization Code
    Grant (RFC 6749 §4.1) and is only reached when the client has
    `require_consent=true`.

    The `consent` field must be `allow` to grant authorization; any other
    value (e.g. `deny`) causes an `access_denied` error redirect to
    `redirect_uri?error=access_denied&state=<state>` per RFC 6749 §4.1.2.1.
    On approval an authorization code is generated and the user-agent is
    redirected to `redirect_uri?code=<code>&state=<state>`.

    The session cookie is required: if the session is missing or invalid the
    endpoint returns HTTP 401. `redirect_uri` is re-validated against the
    client's registered URIs; a mismatch returns HTTP 400 without a redirect.

    PKCE parameters (`code_challenge`, `code_challenge_method`) and the OIDC
    `nonce` submitted by the consent form are bound to the authorization code
    and must be verified by the client when exchanging the code for tokens
    (RFC 7636 §4.6).

    **Specification:**
    - RFC 6749 §4.1 — Authorization Code Grant (consent step)
    - RFC 6749 §4.1.2.1 — Error response via redirect
    - RFC 7636 §4.6 — PKCE code binding
    - OpenID Connect Core 1.0 §3.1 — `nonce` binding

    **Authentication:** session cookie (HTTP 401 if session is absent or
    invalid — this endpoint is not reachable without a prior authenticated
    session established by `GET /oauth2/authorize`)

    **Example:**
    ```
    curl -L -X POST \\
      -H "Cookie: session=<session-token>" \\
      -d "consent=allow" \\
      -d "client_id=my-app" \\
      -d "redirect_uri=https%3A%2F%2Fapp.example.com%2Fcallback" \\
      -d "scope=openid+profile+email" \\
      -d "state=xyzABC123" \\
      -d "code_challenge=E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM" \\
      -d "code_challenge_method=S256" \\
      -d "nonce=n-0S6_WzA2Mj" \\
      https://auth.example.com/oauth2/authorize
    ```
    """
    logger.info("Authorization consent submission: client_id=%s, consent=%s", client_id, consent)

    # Check if user is logged in
    session_token = request.cookies.get(get_session_cookie_name())

    if not session_token:
        logger.warning("Authorization consent failed: not authenticated")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
        )

    user = await session_service.get_user_by_session_token(db, session_token)

    if not user:
        logger.warning("Authorization consent failed: invalid session")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid session",
        )

    # Get client
    client = await oauth2_service.get_client_by_client_id(db, client_id)

    if not client or not client.is_active:
        logger.warning("Authorization consent failed: unknown or inactive client %s", client_id)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Unknown or inactive client",
        )

    # Validate redirect_uri
    if not oauth2_service.validate_redirect_uri(client, redirect_uri):
        logger.warning(
            "Authorization consent failed: invalid redirect_uri for client %s", client_id
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid redirect_uri",
        )

    # Check consent decision
    if consent != "allow":
        logger.info("Authorization denied by user for client %s", client_id)
        return RedirectResponse(
            url=_build_error_redirect(
                redirect_uri,
                OAuth2Error.ACCESS_DENIED,
                "User denied the authorization request",
                state,
            ),
            status_code=status.HTTP_302_FOUND,
        )

    # Parse scopes
    scopes = _parse_scopes(scope)

    # Generate authorization code
    code = await oauth2_service.create_authorization_code(
        db=db,
        client=client,
        user_id=str(user.id),
        redirect_uri=redirect_uri,
        scopes=scopes,
        code_challenge=code_challenge,
        code_challenge_method=code_challenge_method,
        nonce=nonce,
        state=state,
    )

    await db.commit()

    logger.info(
        "Authorization code issued (via consent) for client %s, user %s", client_id, user.id
    )
    return RedirectResponse(
        url=_build_success_redirect(redirect_uri, code, state),
        status_code=status.HTTP_302_FOUND,
    )
