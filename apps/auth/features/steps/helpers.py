# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Small helpers shared by the step modules."""

from unittest.mock import patch

from auth.api.deps import get_encryption
from auth.config import settings
from auth.core.security import AESEncryption


def patch_setting(context, name, value):
    """Override one attribute of the settings singleton until the scenario ends."""
    patcher = patch.object(settings, name, value)
    patcher.start()
    context.add_cleanup(patcher.stop)


def fresh_encryption_key(context):
    """Configure a new random ``JWKS_ENCRYPTION_KEY`` and return the matching cipher."""
    key = AESEncryption.generate_key_b64()
    patch_setting(context, "jwks_encryption_key", key)
    get_encryption.cache_clear()
    context.add_cleanup(get_encryption.cache_clear)
    return AESEncryption.from_base64(key)
