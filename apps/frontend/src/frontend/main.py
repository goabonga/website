# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""FastAPI application entry point."""

from pathlib import Path
from typing import Any

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

from frontend import __version__

from .config import Settings, settings
from .logging import get_logger, setup_logging

logger = get_logger(__name__)

PACKAGE_DIR = Path(__file__).resolve().parent
APP_DIR = PACKAGE_DIR.parents[1]
TEMPLATES_DIR = PACKAGE_DIR / "templates"
DEFAULT_STATIC_DIR = APP_DIR / "web" / "dist"


class HealthResponse(BaseModel):
    """Health check response."""

    status: str


def template_context(cfg: Settings) -> dict[str, Any]:
    """Values injected in the single page application template."""
    return {
        "app_name": cfg.app_name,
        "auth_url": cfg.auth_url,
        "api_url": cfg.api_url,
        "analytics_url": cfg.analytics_url,
        "client_id": cfg.oauth2_client_id,
        "welcome_name": cfg.welcome_name,
        "welcome_words": cfg.welcome_words,
        "legal_company_name": cfg.legal_company_name,
        "legal_address": cfg.legal_address,
        "legal_city": cfg.legal_city,
        "legal_country": cfg.legal_country,
        "legal_director_name": cfg.legal_director_name,
        "legal_host_name": cfg.legal_host_name,
        "legal_host_address": cfg.legal_host_address,
        "legal_host_city": cfg.legal_host_city,
        "legal_host_country": cfg.legal_host_country,
        "legal_host_phone": cfg.legal_host_phone,
        "legal_host_website": cfg.legal_host_website,
        "social_linkedin": cfg.social_linkedin,
        "social_github": cfg.social_github,
        "social_huggingface": cfg.social_huggingface,
    }


def create_app(app_settings: Settings | None = None) -> FastAPI:
    """Build the FastAPI application from the given settings."""
    cfg = app_settings or settings

    app = FastAPI(
        title=cfg.app_name,
        description="""
Frontend application server.

## Features

- **Single Page Application**: Vite-built frontend served via FastAPI
- **Health check**: liveness endpoint for monitoring
- **Logging**: INFO/DEBUG to stdout, WARNING and above to stderr
- **CORS**: configurable cross-origin policy
        """,
        version=__version__,
        debug=cfg.debug,
        docs_url="/docs" if cfg.docs_enabled else None,
        redoc_url="/redoc" if cfg.docs_enabled else None,
        openapi_url="/openapi.json" if cfg.docs_enabled else None,
    )
    app.state.settings = cfg

    app.add_middleware(
        CORSMiddleware,
        allow_origins=cfg.cors_origins,
        allow_credentials=cfg.cors_credentials,
        allow_methods=cfg.cors_methods,
        allow_headers=cfg.cors_headers,
    )

    @app.get("/health", response_model=HealthResponse, include_in_schema=False)
    async def health() -> HealthResponse:
        """Health check endpoint for monitoring."""
        logger.info("Health check requested")
        return HealthResponse(status="healthy")

    # Mount static files (Vite build output)
    static_dir = Path(cfg.static_dir) if cfg.static_dir else DEFAULT_STATIC_DIR
    if static_dir.exists():
        app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

    templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

    # Must stay the last route: it answers every path not handled above.
    @app.get("/{path:path}", response_class=HTMLResponse, include_in_schema=False)
    async def spa_catch_all(request: Request, path: str):
        """Serve the single page application for all unmatched routes."""
        logger.info("SPA route requested: %s", path or "/")
        return templates.TemplateResponse(request, "index.html", template_context(cfg))

    logger.info("Application %s started", cfg.app_name)
    return app


setup_logging(level=settings.log_level)
app = create_app()
