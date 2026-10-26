# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""FastAPI application for MTA-STS service."""

from fastapi import FastAPI
from pydantic import BaseModel

from mta_sts import __version__
from mta_sts.config import settings
from mta_sts.logging import setup_logging
from mta_sts.mta_sts import router as mta_sts_router

# Configure logging
setup_logging(level=settings.log_level)

app = FastAPI(
    title=settings.app_name,
    version=__version__,
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
)


class HealthResponse(BaseModel):
    """Health check response."""

    status: str


@app.get("/health", response_model=HealthResponse, include_in_schema=False)
async def health_check() -> HealthResponse:
    """Health check endpoint."""
    return HealthResponse(status="healthy")


app.include_router(mta_sts_router)
