# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""FastAPI application entry point."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from frontend import __version__

from .config import Settings, settings


class HealthResponse(BaseModel):
    """Health check response."""

    status: str


def create_app(app_settings: Settings | None = None) -> FastAPI:
    """Build the FastAPI application from the given settings."""
    cfg = app_settings or settings

    app = FastAPI(
        title=cfg.app_name,
        description="""
Frontend application server.

## Features

- **Health check**: liveness endpoint for monitoring
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
        return HealthResponse(status="healthy")

    return app


app = create_app()
