# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""FastAPI middleware for request logging and context management."""

import time
import uuid
from collections.abc import Callable

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

from reachy_mini_api.logging import clear_request_context, get_logger, set_request_context

logger = get_logger(__name__)


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """Middleware to log all HTTP requests with user context."""

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """Process request and log with timing and user context."""
        # Generate unique request ID
        request_id = str(uuid.uuid4())[:8]
        request.state.request_id = request_id

        # Start timing
        start_time = time.perf_counter()

        # Extract path and method
        method = request.method
        path = request.url.path

        # Initialize context (user_id and client_id will be set after auth)
        set_request_context(request_id=request_id)

        # Log incoming request
        logger.info(f"REQUEST: {method} {path}")

        try:
            # Process request
            response = await call_next(request)

            # Calculate duration
            duration_ms = (time.perf_counter() - start_time) * 1000

            # Get user context that may have been set during request processing
            user_id = getattr(request.state, "user_id", None)
            client_id = getattr(request.state, "client_id", None)

            # Update context with user info for logging
            if user_id or client_id:
                set_request_context(
                    user_id=user_id,
                    client_id=client_id,
                    request_id=request_id,
                )

            # Log response
            logger.info(
                f"RESPONSE: {method} {path} | "
                f"status={response.status_code} | "
                f"duration={duration_ms:.2f}ms"
            )

            return response

        except Exception as e:
            # Calculate duration even on error
            duration_ms = (time.perf_counter() - start_time) * 1000

            logger.error(
                f"ERROR: {method} {path} | "
                f"error={type(e).__name__}: {e} | "
                f"duration={duration_ms:.2f}ms"
            )
            raise

        finally:
            # Clear context after request
            clear_request_context()
