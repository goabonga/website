# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""API request and response schemas."""

from pydantic import BaseModel, Field


class RootCAResponse(BaseModel):
    """Root CA certificate response."""

    ca_certificate: str = Field(description="Root CA certificate in PEM format")
    fingerprint: str = Field(description="SHA-256 fingerprint of the root CA")
