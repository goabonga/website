# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""FastAPI OAuth2/OIDC Application."""

from pathlib import Path

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.openapi.docs import get_swagger_ui_html, get_swagger_ui_oauth2_redirect_html
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.responses import Response

from auth.api.routes import router
from auth.config import settings
from auth.core.logging import setup_logging
from auth.middlewares import OAuth2CORSMiddleware, SlidingSessionMiddleware, TenantMiddleware

# Configure logging before anything else
setup_logging(settings.log_level)

STATIC_DIR = Path(__file__).parent / "static"

swagger_init_oauth = {
    "clientId": settings.swagger_client_id,
    "usePkceWithAuthorizationCodeGrant": True,
    "scopes": settings.swagger_scopes,
}

swagger_ui_parameters = {
    "persistAuthorization": True,
}

app = FastAPI(
    title=settings.app_title,
    docs_url=None,
    redoc_url=None,
    swagger_ui_init_oauth=swagger_init_oauth,
    swagger_ui_parameters=swagger_ui_parameters,
)

# Templates for error pages
templates_dir = Path(__file__).parent / "templates"
templates = Jinja2Templates(directory=str(templates_dir))

# Mount static files (favicon, swagger CSS/JS)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/docs", include_in_schema=False)
async def custom_swagger_ui():
    """Serve Swagger UI with local static assets (no external CDN dependency)."""
    swagger_js = (
        "/static/swagger-ui-bundle.js"
        if (STATIC_DIR / "swagger-ui-bundle.js").exists()
        else "https://cdn.jsdelivr.net/npm/swagger-ui-dist@5/swagger-ui-bundle.js"
    )
    swagger_css = (
        "/static/swagger-ui.css"
        if (STATIC_DIR / "swagger-ui.css").exists()
        else "https://cdn.jsdelivr.net/npm/swagger-ui-dist@5/swagger-ui.css"
    )
    return get_swagger_ui_html(
        openapi_url=app.openapi_url or "/openapi.json",
        title=f"{app.title} - Docs",
        swagger_js_url=swagger_js,
        swagger_css_url=swagger_css,
        swagger_favicon_url="/static/favicon.ico",
        oauth2_redirect_url="/docs/oauth2-redirect",
        init_oauth=swagger_init_oauth,
        swagger_ui_parameters=swagger_ui_parameters,
    )


@app.get("/docs/oauth2-redirect", include_in_schema=False)
async def swagger_ui_redirect():
    """OAuth2 redirect page for Swagger UI."""
    return get_swagger_ui_oauth2_redirect_html()


def _wants_html(request: Request) -> bool:
    """Check if the request expects an HTML response."""
    accept = request.headers.get("accept", "")
    return "text/html" in accept and "application/json" not in accept


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException) -> Response:
    """Custom exception handler for HTTP errors."""
    if exc.status_code == status.HTTP_403_FORBIDDEN and _wants_html(request):
        return templates.TemplateResponse(
            request=request,
            name="errors/403.html",
            context={"detail": exc.detail},
            status_code=exc.status_code,
            headers=exc.headers,
        )

    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail},
        headers=exc.headers,
    )


app.add_middleware(OAuth2CORSMiddleware)
app.add_middleware(SlidingSessionMiddleware)

# Add tenant middleware only if base domain is configured
if settings.tenant_base_domain:
    app.add_middleware(
        TenantMiddleware,
        base_domain=settings.tenant_base_domain,
        custom_domain_lookup=settings.tenant_custom_domain_lookup,
    )

app.include_router(router)

# Mount uploads directory for serving uploaded files (avatars, etc.)
uploads_path = Path(settings.upload_directory)
uploads_path.mkdir(parents=True, exist_ok=True)
app.mount("/uploads", StaticFiles(directory=str(uploads_path)), name="uploads")
