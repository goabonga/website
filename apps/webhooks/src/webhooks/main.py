# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Webhooks service - Multi-provider webhook receiver."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from webhooks import __version__
from webhooks.config import settings
from webhooks.routes.health import router as health_router

app = FastAPI(
    title=settings.app_name,
    description="Multi-provider webhook receiver and router.",
    version=__version__,
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

# Include routers
app.include_router(health_router)
