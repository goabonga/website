# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""FastAPI main application."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from internal import __version__
from internal.config import settings
from internal.logging import setup_logging

# Configure logging
setup_logging(level=settings.log_level)


app = FastAPI(
    title=settings.app_name,
    description="""
Internal Admin Dashboard for managing platform services.

    """,
    version=__version__,
    docs_url="/docs" if settings.docs_enabled else None,
    redoc_url="/redoc" if settings.docs_enabled else None,
    openapi_url="/openapi.json" if settings.docs_enabled else None,
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=settings.cors_credentials,
    allow_methods=settings.cors_methods,
    allow_headers=settings.cors_headers,
)


class HealthResponse(BaseModel):
    """Health check response."""

    status: str


@app.get("/health", response_model=HealthResponse, include_in_schema=False)
async def health_check() -> HealthResponse:
    """Health check endpoint (hidden from Swagger)."""
    return HealthResponse(status="healthy")
