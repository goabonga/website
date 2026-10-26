# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for the OpenVPN profile generator."""

import pytest
from vpn_portal.core import ovpn
from vpn_portal.core.ovpn import OVPNGeneratorError, generate_ovpn_config, load_ta_key

PARTS = {
    "certificate_pem": "-----BEGIN CERTIFICATE-----\nCLIENT\n-----END CERTIFICATE-----\n\n",
    "private_key_pem": "-----BEGIN RSA PRIVATE KEY-----\nKEY\n-----END RSA PRIVATE KEY-----\n",
    "ca_certificate_pem": "-----BEGIN CERTIFICATE-----\nCA\n-----END CERTIFICATE-----\n",
    "expires_at": "2030-01-01T00:10:00+00:00",
    "ta_key": "-----BEGIN OpenVPN Static key V1-----\nTA\n-----END OpenVPN Static key V1-----\n",
}


def test_profile_uses_the_settings_by_default(monkeypatch):
    monkeypatch.setattr(ovpn.settings, "openvpn_server", "vpn.test")
    monkeypatch.setattr(ovpn.settings, "openvpn_port", 1195)
    monkeypatch.setattr(ovpn.settings, "openvpn_proto", "tcp")

    profile = generate_ovpn_config(**PARTS)

    assert "remote vpn.test 1195" in profile
    assert "proto tcp" in profile
    assert "# Valid until: 2030-01-01T00:10:00+00:00" in profile


def test_explicit_server_overrides_settings():
    profile = generate_ovpn_config(**PARTS, server="other.test", port=443, proto="udp")

    assert "remote other.test 443" in profile
    assert "proto udp" in profile


def test_credentials_are_inlined_in_order():
    profile = generate_ovpn_config(**PARTS)

    sections = [
        "<ca>",
        "</ca>",
        "<cert>",
        "</cert>",
        "<key>",
        "</key>",
        "<tls-auth>",
        "</tls-auth>",
    ]
    positions = [profile.index(section) for section in sections]
    assert positions == sorted(positions)
    assert "key-direction 1" in profile
    assert "<ca>\n-----BEGIN CERTIFICATE-----\nCA\n-----END CERTIFICATE-----\n</ca>" in profile
    assert (
        "<cert>\n-----BEGIN CERTIFICATE-----\nCLIENT\n-----END CERTIFICATE-----\n</cert>" in profile
    )


def test_trailing_newlines_are_stripped():
    profile = generate_ovpn_config(**PARTS)

    assert "\n\n</cert>" not in profile
    assert "\n\n</key>" not in profile
    assert "\n\n</tls-auth>" not in profile


def test_profile_hardening_options():
    profile = generate_ovpn_config(**PARTS)

    for option in ("remote-cert-tls server", "cipher AES-256-GCM", "auth SHA256", "client"):
        assert option in profile.splitlines()


def test_ta_key_is_loaded_from_the_configured_file(tmp_path, monkeypatch):
    ta_file = tmp_path / "ta.key"
    ta_file.write_text("FILE-TA-KEY\n")
    monkeypatch.setattr(ovpn.settings, "openvpn_ta_key_path", str(ta_file))
    parts = {k: v for k, v in PARTS.items() if k != "ta_key"}

    assert load_ta_key() == "FILE-TA-KEY\n"
    assert "<tls-auth>\nFILE-TA-KEY\n</tls-auth>" in generate_ovpn_config(**parts)


def test_missing_ta_key_is_an_error(tmp_path, monkeypatch):
    monkeypatch.setattr(ovpn.settings, "openvpn_ta_key_path", str(tmp_path / "absent.key"))
    parts = {k: v for k, v in PARTS.items() if k != "ta_key"}

    with pytest.raises(OVPNGeneratorError, match="TLS auth key not found"):
        generate_ovpn_config(**parts)
