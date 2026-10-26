# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Health check endpoint."""

from fastapi import APIRouter

from auth.api.schemas.health import HealthResponse

router = APIRouter()


@router.get("/health", response_model=HealthResponse, include_in_schema=False)
async def health() -> HealthResponse:
    """Return a liveness signal for load balancers and container probes.

    Intended for consumption by infrastructure tooling such as load balancers,
    Kubernetes liveness probes, and uptime monitors. The check is deliberately
    dependency-free — it performs no database or cache I/O — so it stays
    responsive even during partial outages. Returns `{"status": "healthy"}` with
    HTTP 200 whenever the application process is alive.

    **Authentication:** none (public endpoint)

    **Example:**
    ```
    curl https://auth.example.com/health
    # {"status":"healthy"}
    ```
    """
    return HealthResponse(status="healthy")
