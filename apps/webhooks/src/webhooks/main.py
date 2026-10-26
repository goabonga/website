# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Webhooks service - Multi-provider webhook receiver."""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from webhooks import __version__
from webhooks.config import settings
from webhooks.logging import get_logger, setup_logging
from webhooks.routes.health import router as health_router

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler."""
    setup_logging(level=settings.log_level)
    logger.info("Webhooks service starting")
    yield
    logger.info("Webhooks service shutting down")


app = FastAPI(
    title=settings.app_name,
    description="Multi-provider webhook receiver and router.",
    version=__version__,
    docs_url="/docs" if settings.docs_enabled else None,
    redoc_url="/redoc" if settings.docs_enabled else None,
    openapi_url="/openapi.json" if settings.docs_enabled else None,
    lifespan=lifespan,
)

# CORS middleware
if settings.cors_origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=settings.cors_credentials,
        allow_methods=settings.cors_methods,
        allow_headers=settings.cors_headers,
    )

# Include routers
app.include_router(health_router)

# Register webhook routes based on configuration
if settings.brevo_enabled:
    from webhooks.routes.brevo import router as brevo_router

    app.include_router(brevo_router, prefix="/webhooks/brevo", tags=["brevo"])

if settings.ses_enabled:
    from webhooks.routes.ses import router as ses_router

    app.include_router(ses_router, prefix="/webhooks/ses", tags=["ses"])
