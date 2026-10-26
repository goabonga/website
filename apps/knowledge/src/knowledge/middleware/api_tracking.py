# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""API call tracking middleware."""

import logging

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import Response

from knowledge.database import async_session_factory
from knowledge.services.quotas import QuotaService

logger = logging.getLogger(__name__)


class APITrackingMiddleware(BaseHTTPMiddleware):
    """Middleware to track API calls for quota management.

    Tracks requests to /api/v1/ endpoints (and /v1/ for backward compatibility).
    Records successful API calls per tenant for usage statistics.
    """

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        # Only track API routes
        if not request.url.path.startswith(("/api/v1/", "/v1/")):
            return await call_next(request)

        # Skip health check endpoint
        if request.url.path in ("/api/v1/health", "/v1/health", "/health"):
            return await call_next(request)

        # Process the request
        response = await call_next(request)

        # Only record successful API calls (2xx status codes)
        if 200 <= response.status_code < 300:
            # Get tenant_id from request state (set by auth dependency)
            tenant_id = getattr(request.state, "tenant_id", None)

            if tenant_id:
                try:
                    async with async_session_factory() as db:
                        quota_service = QuotaService(db)
                        await quota_service.record_api_call(tenant_id)
                        await db.commit()
                except Exception as e:
                    # Don't fail the request if tracking fails
                    logger.warning(f"Failed to record API call: {e}")

        return response
