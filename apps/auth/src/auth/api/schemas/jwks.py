# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Public JWKS (JSON Web Key Set) response schemas."""

from pydantic import BaseModel, Field


class PublicJWK(BaseModel):
    """Public JSON Web Key (RFC 7517) — never includes private key material."""

    kty: str = Field(..., description="Key type (e.g. 'RSA', 'EC')")
    use: str | None = Field(None, description="Public key use ('sig' for signature)")
    alg: str | None = Field(
        None, description="Algorithm intended for use with the key (e.g. 'RS256')"
    )
    kid: str = Field(..., description="Key ID used to match a specific key")
    n: str | None = Field(None, description="RSA modulus, base64url-encoded (RSA keys)")
    e: str | None = Field(None, description="RSA public exponent, base64url-encoded (RSA keys)")


class JWKSResponse(BaseModel):
    """JWK Set response (RFC 7517 §5)."""

    keys: list[PublicJWK] = Field(..., description="Array of public JWKs")
