# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Pydantic schemas for /api/v1/jwks admin endpoints."""

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel


class GenerateKeyRequest(BaseModel):
    """Request body for generating a new JWK.

    Attributes:
        key_size: RSA key size in bits (2048, 3072, or 4096). Defaults to None
            which means the service default (2048) is used.
        activate: If True, the newly generated key is activated immediately
            (all other keys are deactivated).
    """

    key_size: Literal[2048, 3072, 4096] | None = None
    activate: bool = False


class RotateKeysRequest(BaseModel):
    """Request body for rotating the active signing key.

    Attributes:
        key_size: RSA key size in bits (2048, 3072, or 4096) for the new key.
            Defaults to None which means the service default (2048) is used.
    """

    key_size: Literal[2048, 3072, 4096] | None = None


class JWKResponse(BaseModel):
    """Response for a single JWK (never exposes private key)."""

    id: uuid.UUID
    kid: str
    kty: str
    alg: str
    use: str
    is_active: bool
    revoked_at: datetime | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class JWKRotateResponse(BaseModel):
    """Response after key rotation."""

    message: str
    new_key: JWKResponse
