# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Main FastAPI application."""

import traceback
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from custom_domain import __version__
from custom_domain.config import settings
from custom_domain.database import engine
from custom_domain.logging import get_logger
from custom_domain.routes import health

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager."""
    logger.info("Starting Custom Domain Service")

    yield

    logger.info("Shutting down Custom Domain Service")
    await engine.dispose()


app = FastAPI(
    title="Custom Domain Service",
    description="Centralized service for managing custom domains with SSL provisioning.",
    version=__version__,
    lifespan=lifespan,
    docs_url="/docs" if settings.docs_enabled else None,
    redoc_url="/redoc" if settings.docs_enabled else None,
    openapi_url="/openapi.json" if settings.docs_enabled else None,
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


# Exception handler for debugging (logs full traceback)
@app.exception_handler(Exception)
async def debug_exception_handler(request: Request, exc: Exception):
    """Log full exception traceback for debugging."""
    tb = traceback.format_exception(type(exc), exc, exc.__traceback__)
    logger.error("Unhandled exception: %s", exc)
    logger.error("Traceback:\n%s", "".join(tb))
    # Also print to stdout for CI visibility
    print(f"[FastAPI Error] {type(exc).__name__}: {exc}")
    print(f"[FastAPI Traceback]\n{''.join(tb)}")
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal Server Error", "error": str(exc)},
    )


# Health check
app.include_router(health.router)


@app.get("/")
async def root():
    """Root endpoint."""
    return {
        "service": "custom-domain",
        "version": __version__,
        "docs": "/docs" if settings.docs_enabled else None,
    }
