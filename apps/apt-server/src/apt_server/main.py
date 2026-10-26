# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""FastAPI application entry point.

Served by gunicorn with uvicorn workers.
Default module path: apt_server.main:app
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.docs import get_swagger_ui_html, get_swagger_ui_oauth2_redirect_html
from fastapi.staticfiles import StaticFiles

from apt_server.config import settings
from apt_server.logging import get_logger, setup_logging

setup_logging(settings.log_level)
logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(application: FastAPI) -> AsyncIterator[None]:
    """Startup and shutdown events."""
    logger.info("starting %s", settings.app_name)
    yield
    logger.info("shutting down %s", settings.app_name)


swagger_config: dict = {}

app = FastAPI(
    title=settings.app_name,
    docs_url=None,
    redoc_url=None,
    lifespan=lifespan,
    **swagger_config,
)


STATIC_DIR = Path(__file__).parent / "static"

# Mount static files (favicon, swagger CSS/JS overrides)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


if settings.docs_enabled:

    @app.get("/docs", include_in_schema=False)
    async def custom_swagger_ui():
        """Serve Swagger UI with custom static assets.

        Place files in apt_server/static/:
          - favicon.ico  — custom favicon
          - swagger.css  — custom CSS (optional)
          - swagger.js   — custom JS (optional)
        Falls back to CDN defaults when local files are absent.
        """
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
            openapi_url=app.openapi_url,
            title=f"{settings.app_name} - Docs",
            swagger_js_url=swagger_js,
            swagger_css_url=swagger_css,
            swagger_favicon_url="/static/favicon.ico",
            oauth2_redirect_url="/docs/oauth2-redirect",
            **swagger_config,
        )

    @app.get(app.swagger_ui_oauth2_redirect_url, include_in_schema=False)
    async def swagger_ui_redirect():
        """OAuth2 redirect page for Swagger UI."""
        return get_swagger_ui_oauth2_redirect_html()


app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.all_cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health", include_in_schema=False)
async def health() -> dict[str, str]:
    """Health check endpoint."""
    return {"status": "ok"}
