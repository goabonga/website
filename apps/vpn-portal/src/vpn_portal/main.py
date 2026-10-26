# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""VPN Portal - FastAPI application."""

from contextlib import asynccontextmanager

from fastapi import FastAPI

from vpn_portal import __version__
from vpn_portal.api.routes import router
from vpn_portal.config import settings
from vpn_portal.logging import get_logger, setup_logging

# Setup logging before anything else
setup_logging(settings.log_level)
logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler."""
    logger.info("VPN Portal starting")
    yield
    logger.info("VPN Portal shutting down")


app = FastAPI(
    title=settings.app_name,
    description="Zero-Trust VPN authentication and certificate issuance service.",
    version=__version__,
    docs_url="/docs" if settings.docs_enabled else None,
    redoc_url="/redoc" if settings.docs_enabled else None,
    openapi_url="/openapi.json" if settings.docs_enabled else None,
    lifespan=lifespan,
)

# Include API routes
app.include_router(router)
