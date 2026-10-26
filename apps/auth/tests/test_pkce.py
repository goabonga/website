# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for auth.services.pkce — PKCE (RFC 7636) functions."""

import pytest
from auth.services.pkce import (
    generate_code_challenge,
    generate_code_verifier,
    is_valid_code_challenge,
    is_valid_code_challenge_method,
    is_valid_code_verifier,
    verify_code_challenge,
)


class TestGenerateCodeVerifier:
    def test_default_length(self):
        verifier = generate_code_verifier()
        assert len(verifier) == 64

    def test_custom_length(self):
        verifier = generate_code_verifier(length=43)
        assert len(verifier) == 43

    def test_max_length(self):
        verifier = generate_code_verifier(length=128)
        assert len(verifier) == 128

    def test_too_short_falls_back_to_default(self):
        verifier = generate_code_verifier(length=10)
        assert len(verifier) == 64

    def test_too_long_falls_back_to_default(self):
        verifier = generate_code_verifier(length=200)
        assert len(verifier) == 64

    def test_randomness(self):
        v1 = generate_code_verifier()
        v2 = generate_code_verifier()
        assert v1 != v2


class TestGenerateCodeChallenge:
    def test_s256_method(self):
        verifier = "dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk"
        challenge = generate_code_challenge(verifier, "S256")
        assert challenge  # non-empty
        assert "=" not in challenge  # base64url without padding

    def test_plain_method(self):
        verifier = "plain_verifier_value"
        challenge = generate_code_challenge(verifier, "plain")
        assert challenge == verifier

    def test_unsupported_method_raises(self):
        with pytest.raises(ValueError, match="Unsupported"):
            generate_code_challenge("verifier", "RS256")

    def test_s256_deterministic(self):
        verifier = "test_verifier_123"
        c1 = generate_code_challenge(verifier, "S256")
        c2 = generate_code_challenge(verifier, "S256")
        assert c1 == c2


class TestVerifyCodeChallenge:
    def test_s256_valid(self):
        verifier = generate_code_verifier()
        challenge = generate_code_challenge(verifier, "S256")
        assert verify_code_challenge(verifier, challenge, "S256") is True

    def test_s256_invalid(self):
        verifier = generate_code_verifier()
        challenge = generate_code_challenge(verifier, "S256")
        assert verify_code_challenge("wrong_verifier_" + "x" * 43, challenge, "S256") is False

    def test_plain_valid(self):
        verifier = generate_code_verifier()
        challenge = generate_code_challenge(verifier, "plain")
        assert verify_code_challenge(verifier, challenge, "plain") is True

    def test_plain_invalid(self):
        assert verify_code_challenge("a" * 43, "b" * 43, "plain") is False

    def test_invalid_method_returns_false(self):
        assert verify_code_challenge("v", "c", "unknown") is False


class TestIsValidCodeVerifier:
    def test_valid_verifier(self):
        verifier = generate_code_verifier()
        assert is_valid_code_verifier(verifier) is True

    def test_empty_string(self):
        assert is_valid_code_verifier("") is False

    def test_too_short(self):
        assert is_valid_code_verifier("a" * 42) is False

    def test_minimum_length(self):
        assert is_valid_code_verifier("a" * 43) is True

    def test_maximum_length(self):
        assert is_valid_code_verifier("a" * 128) is True

    def test_too_long(self):
        assert is_valid_code_verifier("a" * 129) is False

    def test_valid_characters(self):
        # A-Z, a-z, 0-9, -, ., _, ~
        verifier = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqr0123456789-._~"
        assert is_valid_code_verifier(verifier) is True

    def test_invalid_characters(self):
        verifier = "a" * 42 + " invalid!@#$%^&*()" + "b" * 30
        assert is_valid_code_verifier(verifier) is False


class TestIsValidCodeChallenge:
    def test_valid_challenge(self):
        verifier = generate_code_verifier()
        challenge = generate_code_challenge(verifier, "S256")
        assert is_valid_code_challenge(challenge) is True

    def test_empty_string(self):
        assert is_valid_code_challenge("") is False

    def test_invalid_characters(self):
        assert is_valid_code_challenge("invalid challenge!") is False


class TestIsValidCodeChallengeMethod:
    def test_s256(self):
        assert is_valid_code_challenge_method("S256") is True

    def test_plain(self):
        assert is_valid_code_challenge_method("plain") is True

    def test_invalid(self):
        assert is_valid_code_challenge_method("RS256") is False
        assert is_valid_code_challenge_method("") is False
