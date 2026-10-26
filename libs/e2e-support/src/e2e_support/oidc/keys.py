# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""The RS256 key the fake provider signs its tokens with."""

from __future__ import annotations

import secrets
from typing import Any

import jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

#: Size of the generated RSA key, in bits.
KEY_SIZE = 2048


class SigningKey:
    """An RSA key pair generated at construction time, with its ``kid``."""

    def __init__(self, kid: str | None = None) -> None:
        self.kid = kid or secrets.token_hex(8)
        self._private = rsa.generate_private_key(public_exponent=65537, key_size=KEY_SIZE)
        self._pem = self._private.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )

    def public_jwk(self) -> dict[str, Any]:
        """The public key as a JWK, ready for a JWKS document."""
        jwk = jwt.algorithms.RSAAlgorithm.to_jwk(self._private.public_key(), as_dict=True)
        jwk.pop("key_ops", None)
        return {**jwk, "kid": self.kid, "use": "sig", "alg": "RS256"}

    def sign(self, claims: dict[str, Any]) -> str:
        """Encode ``claims`` as an RS256 JWT carrying this key's ``kid``."""
        return jwt.encode(claims, self._pem, algorithm="RS256", headers={"kid": self.kid})
