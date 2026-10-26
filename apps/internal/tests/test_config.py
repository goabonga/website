# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for application configuration."""

import os
from unittest.mock import patch

from internal.config import get_credential


class TestGetCredential:
    def test_returns_env_var(self):
        with patch.dict(os.environ, {"MY_SECRET": "from-env"}, clear=False):
            result = get_credential("MY_SECRET", "default")
            assert result == "from-env"

    def test_returns_default_when_no_env(self):
        with patch.dict(os.environ, {}, clear=False):
            env_key = "NONEXISTENT_SECRET_FOR_TEST"
            os.environ.pop(env_key, None)
            result = get_credential(env_key, "default-val")
            assert result == "default-val"

    def test_reads_from_credentials_directory(self, tmp_path):
        cred_file = tmp_path / "MY_CRED"
        cred_file.write_text("  secret-from-file  \n")

        with patch.dict(os.environ, {"CREDENTIALS_DIRECTORY": str(tmp_path)}, clear=False):
            result = get_credential("MY_CRED", "default")
            assert result == "secret-from-file"

    def test_credentials_dir_file_not_found_falls_back(self, tmp_path):
        with patch.dict(
            os.environ,
            {"CREDENTIALS_DIRECTORY": str(tmp_path), "MISSING_CRED": "env-val"},
            clear=False,
        ):
            result = get_credential("MISSING_CRED", "default")
            assert result == "env-val"

    def test_no_credentials_dir(self):
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("CREDENTIALS_DIRECTORY", None)
            os.environ.pop("NO_SUCH_CRED", None)
            result = get_credential("NO_SUCH_CRED", "fallback")
            assert result == "fallback"
