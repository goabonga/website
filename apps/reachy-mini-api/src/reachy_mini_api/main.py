# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Reachy Mini API application."""

import contextlib
import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from reachy_mini_api import __version__
from reachy_mini_api.api import router as api_router
from reachy_mini_api.auth import jwks_manager
from reachy_mini_api.config import settings
from reachy_mini_api.logging import get_logger, log_action, setup_logging
from reachy_mini_api.middleware import RequestLoggingMiddleware

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Application lifespan handler."""
    setup_logging(level=settings.log_level)
    logger.info(f"Starting {settings.app_name}")
    yield
    logger.info(f"Shutting down {settings.app_name}")
    await jwks_manager.close()


def get_swagger_ui_oauth2_config() -> dict:
    """Build Swagger UI OAuth2 configuration if OAuth2 is configured."""
    if not settings.oauth2_issuer or not settings.oauth2_swagger_client_id:
        return {}

    return {
        "swagger_ui_init_oauth": {
            "clientId": settings.oauth2_swagger_client_id,
            "usePkceWithAuthorizationCodeGrant": True,
        },
        "swagger_ui_parameters": {
            "persistAuthorization": True,
        },
    }


class ConnectionManager:
    """Manage WebSocket connections for real-time robot communication."""

    def __init__(self):
        self.active_connections: list[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        self.active_connections.remove(websocket)

    async def send_personal_message(self, message: dict, websocket: WebSocket):
        await websocket.send_json(message)

    async def broadcast(self, message: dict):
        for connection in self.active_connections:
            with contextlib.suppress(Exception):
                await connection.send_json(message)


manager = ConnectionManager()

swagger_config = get_swagger_ui_oauth2_config()


app = FastAPI(
    title=settings.app_name,
    description="""
Internal API for the Reachy Mini robot to fetch reports and data.

## Features

- **Reports**: Fetch daily briefings and quick updates
- **Notifications**: Pending notification feed
- **Status**: Server and monitored services status
- **WebSocket**: Bidirectional communication with robot
- **OAuth2 authentication**: PKCE-based authentication with scope validation

## Authentication

This API uses OAuth2 with PKCE for authentication. The Swagger UI requests
only `openid`, `profile`, and `email` scopes. Routes validate the bearer
token against the issuer JWKS and check the scopes it carries.

## Required Scopes

- `reachy:reports:read` - Read robot reports
- `reachy:notifications:read` - Read notifications
- `reachy:status:read` - Read status information
""",
    version=__version__,
    docs_url="/docs" if settings.docs_enabled else None,
    redoc_url="/redoc" if settings.docs_enabled else None,
    openapi_url="/openapi.json" if settings.docs_enabled else None,
    lifespan=lifespan,
    **swagger_config,
)

# Request logging middleware (added first so that it wraps every request)
app.add_middleware(RequestLoggingMiddleware)

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


app.include_router(api_router, prefix="/api")


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket endpoint for real-time robot communication.

    Messages are JSON objects with a ``type`` field. Every reply carries a
    ``timestamp``.

    Supported incoming message types:
    - ping: Returns a pong response
    - status: Returns the number of active connections
    - broadcast: Sends ``data`` to every connected client
    - anything else: Returns an ack echoing the received message

    Text that is not valid JSON returns an error message.
    """
    # Get client info for logging
    client_host = websocket.client.host if websocket.client else "unknown"
    connection_id = id(websocket)

    await manager.connect(websocket)
    log_action(logger, "websocket_connect", client_id=client_host, connection_id=connection_id)

    try:
        # Send welcome message
        await manager.send_personal_message(
            {
                "type": "connected",
                "message": "Connected to Reachy Mini API",
                "timestamp": datetime.now(UTC).isoformat(),
            },
            websocket,
        )

        while True:
            # Receive message from client
            data = await websocket.receive_text()
            try:
                message = json.loads(data)
                msg_type = message.get("type", "unknown")

                # Log all WebSocket messages
                log_action(
                    logger,
                    "websocket_message",
                    client_id=client_host,
                    message_type=msg_type,
                    connection_id=connection_id,
                )

                if msg_type == "ping":
                    await manager.send_personal_message(
                        {
                            "type": "pong",
                            "timestamp": datetime.now(UTC).isoformat(),
                        },
                        websocket,
                    )
                elif msg_type == "status":
                    await manager.send_personal_message(
                        {
                            "type": "status",
                            "connections": len(manager.active_connections),
                            "timestamp": datetime.now(UTC).isoformat(),
                        },
                        websocket,
                    )
                elif msg_type == "broadcast":
                    log_action(
                        logger,
                        "websocket_broadcast",
                        client_id=client_host,
                        connection_id=connection_id,
                    )
                    # Broadcast message to all connected clients
                    await manager.broadcast(
                        {
                            "type": "broadcast",
                            "data": message.get("data", {}),
                            "timestamp": datetime.now(UTC).isoformat(),
                        }
                    )
                else:
                    # Echo back unknown messages with acknowledgment
                    await manager.send_personal_message(
                        {
                            "type": "ack",
                            "received": message,
                            "timestamp": datetime.now(UTC).isoformat(),
                        },
                        websocket,
                    )
            except json.JSONDecodeError:
                logger.warning(f"Invalid JSON from client {client_host}")
                await manager.send_personal_message(
                    {
                        "type": "error",
                        "message": "Invalid JSON",
                        "timestamp": datetime.now(UTC).isoformat(),
                    },
                    websocket,
                )
    except WebSocketDisconnect:
        manager.disconnect(websocket)
        log_action(
            logger, "websocket_disconnect", client_id=client_host, connection_id=connection_id
        )
