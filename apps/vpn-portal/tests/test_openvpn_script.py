# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for the OpenVPN hook script (scripts/openvpn.py)."""

from __future__ import annotations

import json
import os
import time
from unittest.mock import MagicMock, patch

import httpx
import pytest

# Module-level constants are set at import time from env vars,
# so we must set env before importing.
os.environ.setdefault("OPENVPN_OAUTH2_CLIENT_ID", "test-client")
os.environ.setdefault("OPENVPN_OAUTH2_CLIENT_SECRET", "test-secret")
os.environ.setdefault("OPENVPN_OAUTH2_TOKEN_URL", "https://auth.example.com/oauth2/token")
os.environ.setdefault("OPENVPN_API_BASE_URL", "http://127.0.0.1:8000")
os.environ.setdefault("OPENVPN_TOKEN_CACHE_PATH", "/tmp/test-token.json")

from scripts.openvpn import (
    _cidr_to_netmask,
    _get_config_file_path,
    _get_credential,
    _kill_client_via_management,
    _load_cached_token,
    _management_send,
    _save_cached_token,
    _write_routes,
    get_access_token,
    handle_connect,
    handle_disconnect,
    handle_reneg,
    main,
)

# ---------------------------------------------------------------------------
# _get_credential
# ---------------------------------------------------------------------------


class TestGetCredential:
    def test_reads_from_credentials_directory(self, tmp_path, monkeypatch):
        cred_file = tmp_path / "MY_SECRET"
        cred_file.write_text("  secret-value  \n")
        monkeypatch.setenv("CREDENTIALS_DIRECTORY", str(tmp_path))

        assert _get_credential("MY_SECRET") == "secret-value"

    def test_falls_back_to_env_var(self, monkeypatch):
        monkeypatch.delenv("CREDENTIALS_DIRECTORY", raising=False)
        monkeypatch.setenv("MY_SECRET", "env-value")

        assert _get_credential("MY_SECRET") == "env-value"

    def test_returns_default_when_missing(self, monkeypatch):
        monkeypatch.delenv("CREDENTIALS_DIRECTORY", raising=False)
        monkeypatch.delenv("NONEXISTENT", raising=False)

        assert _get_credential("NONEXISTENT", "fallback") == "fallback"

    def test_creds_dir_missing_file_falls_back(self, tmp_path, monkeypatch):
        monkeypatch.setenv("CREDENTIALS_DIRECTORY", str(tmp_path))
        monkeypatch.setenv("MY_SECRET", "env-value")

        assert _get_credential("MY_SECRET") == "env-value"


# ---------------------------------------------------------------------------
# CIDR conversion
# ---------------------------------------------------------------------------


class TestCidrToNetmask:
    @pytest.mark.parametrize(
        "prefix,expected",
        [
            (0, "0.0.0.0"),
            (8, "255.0.0.0"),
            (16, "255.255.0.0"),
            (24, "255.255.255.0"),
            (32, "255.255.255.255"),
            (20, "255.255.240.0"),
        ],
    )
    def test_conversion(self, prefix, expected):
        assert _cidr_to_netmask(prefix) == expected


# ---------------------------------------------------------------------------
# Token caching
# ---------------------------------------------------------------------------


class TestTokenCache:
    def test_load_returns_none_when_no_file(self, monkeypatch):
        monkeypatch.setattr("scripts.openvpn.TOKEN_CACHE_PATH", "/tmp/nonexistent-token.json")
        assert _load_cached_token() is None

    def test_save_and_load(self, tmp_path, monkeypatch):
        cache_file = tmp_path / "token.json"
        monkeypatch.setattr("scripts.openvpn.TOKEN_CACHE_PATH", str(cache_file))

        _save_cached_token("my-token", 3600)
        assert cache_file.exists()

        token = _load_cached_token()
        assert token == "my-token"

    def test_expired_token_returns_none(self, tmp_path, monkeypatch):
        cache_file = tmp_path / "token.json"
        monkeypatch.setattr("scripts.openvpn.TOKEN_CACHE_PATH", str(cache_file))

        # Write a token that expired 100 seconds ago
        data = {"access_token": "old-token", "expires_at": time.time() - 100}
        cache_file.write_text(json.dumps(data))

        assert _load_cached_token() is None

    def test_corrupt_json_returns_none(self, tmp_path, monkeypatch):
        cache_file = tmp_path / "token.json"
        cache_file.write_text("not-json")
        monkeypatch.setattr("scripts.openvpn.TOKEN_CACHE_PATH", str(cache_file))

        assert _load_cached_token() is None


# ---------------------------------------------------------------------------
# Write routes
# ---------------------------------------------------------------------------


class TestWriteRoutes:
    def test_writes_push_directives(self, tmp_path):
        config_file = tmp_path / "client.conf"
        _write_routes(str(config_file), ["10.8.0.0/24", "192.168.1.0/16"])

        content = config_file.read_text()
        assert 'push "route 10.8.0.0 255.255.255.0"' in content
        assert 'push "route 192.168.1.0 255.255.0.0"' in content

    def test_skips_invalid_routes(self, tmp_path):
        config_file = tmp_path / "client.conf"
        _write_routes(str(config_file), ["invalid-route", "10.0.0.0/8"])

        content = config_file.read_text()
        assert "invalid-route" not in content
        assert 'push "route 10.0.0.0 255.0.0.0"' in content

    def test_handles_write_error(self, tmp_path):
        # Writing to a non-existent directory should not raise
        _write_routes("/nonexistent/dir/file.conf", ["10.0.0.0/8"])


# ---------------------------------------------------------------------------
# _get_config_file_path
# ---------------------------------------------------------------------------


class TestGetConfigFilePath:
    def test_extracts_temp_file(self, monkeypatch):
        monkeypatch.setattr(
            "sys.argv",
            ["/opt/vpn-portal/bin/openvpn-connect", "--connect", "/tmp/openvpn_cc_123.tmp"],
        )
        assert _get_config_file_path() == "/tmp/openvpn_cc_123.tmp"

    def test_returns_none_when_no_positional(self, monkeypatch):
        monkeypatch.setattr("sys.argv", ["/opt/vpn-portal/bin/openvpn-connect", "--connect"])
        assert _get_config_file_path() is None


# ---------------------------------------------------------------------------
# OAuth2 token acquisition
# ---------------------------------------------------------------------------


class TestGetAccessToken:
    def test_returns_cached_token(self, monkeypatch):
        monkeypatch.setattr("scripts.openvpn._load_cached_token", lambda: "cached-token")

        client = MagicMock()
        assert get_access_token(client) == "cached-token"
        client.post.assert_not_called()

    def test_fetches_new_token(self, monkeypatch):
        monkeypatch.setattr("scripts.openvpn._load_cached_token", lambda: None)
        monkeypatch.setattr("scripts.openvpn.CLIENT_ID", "test-id")
        monkeypatch.setattr("scripts.openvpn.CLIENT_SECRET", "test-secret")
        monkeypatch.setattr("scripts.openvpn.TOKEN_URL", "https://auth.example.com/token")

        saved = {}
        monkeypatch.setattr(
            "scripts.openvpn._save_cached_token",
            lambda t, e: saved.update({"token": t, "expires": e}),
        )

        response = MagicMock()
        response.json.return_value = {"access_token": "new-token", "expires_in": 3600}
        client = MagicMock()
        client.post.return_value = response

        assert get_access_token(client) == "new-token"
        assert saved["token"] == "new-token"

    def test_exits_when_not_configured(self, monkeypatch):
        monkeypatch.setattr("scripts.openvpn._load_cached_token", lambda: None)
        monkeypatch.setattr("scripts.openvpn.CLIENT_ID", "")
        monkeypatch.setattr("scripts.openvpn.CLIENT_SECRET", "")
        monkeypatch.setattr("scripts.openvpn.TOKEN_URL", "")

        with pytest.raises(SystemExit):
            get_access_token(MagicMock())

    def test_exits_on_http_error(self, monkeypatch):
        monkeypatch.setattr("scripts.openvpn._load_cached_token", lambda: None)
        monkeypatch.setattr("scripts.openvpn.CLIENT_ID", "test-id")
        monkeypatch.setattr("scripts.openvpn.CLIENT_SECRET", "test-secret")
        monkeypatch.setattr("scripts.openvpn.TOKEN_URL", "https://auth.example.com/token")

        client = MagicMock()
        client.post.side_effect = httpx.HTTPError("connection failed")

        with pytest.raises(SystemExit):
            get_access_token(client)


# ---------------------------------------------------------------------------
# handle_connect
# ---------------------------------------------------------------------------


class TestHandleConnect:
    def _mock_client(self, validate_resp, connect_resp=None):
        client = MagicMock()
        responses = [validate_resp]
        if connect_resp:
            responses.append(connect_resp)
        client.post.side_effect = responses
        return client

    def test_allows_valid_certificate(self, monkeypatch, tmp_path):
        monkeypatch.setenv("common_name", "vpn-user@example.com")
        monkeypatch.setenv("untrusted_ip", "1.2.3.4")
        monkeypatch.setenv("ifconfig_pool_remote_ip", "10.8.0.6")
        monkeypatch.setattr(
            "sys.argv",
            ["/opt/vpn-portal/bin/openvpn-connect", "--connect", str(tmp_path / "cc.tmp")],
        )

        validate = MagicMock(status_code=200)
        validate.json.return_value = {"valid": True, "routes": ["10.8.0.0/24"]}
        connect = MagicMock(status_code=200)

        client = self._mock_client(validate, connect)
        assert handle_connect(client, "token") == 0

    def test_denies_invalid_certificate(self, monkeypatch):
        monkeypatch.setenv("common_name", "revoked-user")
        monkeypatch.setenv("untrusted_ip", "1.2.3.4")
        monkeypatch.setenv("ifconfig_pool_remote_ip", "10.8.0.6")

        validate = MagicMock(status_code=200)
        validate.json.return_value = {"valid": False, "reason": "certificate revoked"}

        client = self._mock_client(validate)
        assert handle_connect(client, "token") == 1

    def test_denies_on_api_error(self, monkeypatch):
        monkeypatch.setenv("common_name", "user")
        monkeypatch.setenv("untrusted_ip", "1.2.3.4")
        monkeypatch.setenv("ifconfig_pool_remote_ip", "10.8.0.6")

        validate = MagicMock(status_code=500, text="Internal Server Error")

        client = self._mock_client(validate)
        assert handle_connect(client, "token") == 1

    def test_denies_missing_common_name(self, monkeypatch):
        monkeypatch.delenv("common_name", raising=False)
        assert handle_connect(MagicMock(), "token") == 1


# ---------------------------------------------------------------------------
# handle_disconnect
# ---------------------------------------------------------------------------


class TestHandleDisconnect:
    def test_records_disconnection(self, monkeypatch):
        monkeypatch.setenv("common_name", "vpn-user")
        monkeypatch.setenv("bytes_received", "1024")
        monkeypatch.setenv("bytes_sent", "2048")

        resp = MagicMock(status_code=200)
        client = MagicMock()
        client.post.return_value = resp

        assert handle_disconnect(client, "token") == 0

    def test_returns_error_on_api_failure(self, monkeypatch):
        monkeypatch.setenv("common_name", "vpn-user")
        monkeypatch.setenv("bytes_received", "0")
        monkeypatch.setenv("bytes_sent", "0")

        resp = MagicMock(status_code=500, text="error")
        client = MagicMock()
        client.post.return_value = resp

        assert handle_disconnect(client, "token") == 1

    def test_missing_common_name(self, monkeypatch):
        monkeypatch.delenv("common_name", raising=False)
        assert handle_disconnect(MagicMock(), "token") == 1


# ---------------------------------------------------------------------------
# handle_reneg
# ---------------------------------------------------------------------------


class TestHandleReneg:
    def test_accepts_ca_chain_depth(self, monkeypatch):
        monkeypatch.setattr("sys.argv", ["script", "--reneg", "1", "CN=CA"])
        assert handle_reneg(MagicMock(), "token") == 0

    def test_validates_client_cert_at_depth_0(self, monkeypatch):
        monkeypatch.setattr("sys.argv", ["script", "--reneg", "0", "CN=user"])
        monkeypatch.setenv("common_name", "vpn-user")
        monkeypatch.setenv("untrusted_ip", "1.2.3.4")

        resp = MagicMock(status_code=200)
        resp.json.return_value = {"valid": True}
        client = MagicMock()
        client.post.return_value = resp

        assert handle_reneg(client, "token") == 0

    def test_rejects_revoked_cert(self, monkeypatch):
        monkeypatch.setattr("sys.argv", ["script", "--reneg", "0", "CN=user"])
        monkeypatch.setenv("common_name", "vpn-user")
        monkeypatch.setenv("untrusted_ip", "1.2.3.4")
        monkeypatch.setenv("untrusted_port", "36201")

        resp = MagicMock(status_code=200)
        resp.json.return_value = {"valid": False, "reason": "revoked"}
        client = MagicMock()
        client.post.return_value = resp

        with patch("scripts.openvpn._kill_client_via_management") as mock_kill:
            result = handle_reneg(client, "token")
            assert result == 1
            mock_kill.assert_called_once_with("1.2.3.4:36201")

    def test_fails_open_on_api_exception(self, monkeypatch):
        monkeypatch.setattr("sys.argv", ["script", "--reneg", "0", "CN=user"])
        monkeypatch.setenv("common_name", "vpn-user")
        monkeypatch.setenv("untrusted_ip", "1.2.3.4")

        client = MagicMock()
        client.post.side_effect = Exception("connection refused")

        assert handle_reneg(client, "token") == 0

    def test_api_error_triggers_kill(self, monkeypatch):
        monkeypatch.setattr("sys.argv", ["script", "--reneg", "0", "CN=user"])
        monkeypatch.setenv("common_name", "vpn-user")
        monkeypatch.setenv("untrusted_ip", "1.2.3.4")
        monkeypatch.setenv("untrusted_port", "5000")

        resp = MagicMock(status_code=500, text="error")
        client = MagicMock()
        client.post.return_value = resp

        with patch("scripts.openvpn._kill_client_via_management") as mock_kill:
            result = handle_reneg(client, "token")
            assert result == 1
            mock_kill.assert_called_once_with("1.2.3.4:5000")

    def test_missing_common_name(self, monkeypatch):
        monkeypatch.setattr("sys.argv", ["script", "--reneg", "0", "CN=user"])
        monkeypatch.delenv("common_name", raising=False)
        monkeypatch.delenv("X509_0_CN", raising=False)

        assert handle_reneg(MagicMock(), "token") == 1

    def test_uses_x509_cn_fallback(self, monkeypatch):
        monkeypatch.setattr("sys.argv", ["script", "--reneg", "0", "CN=user"])
        monkeypatch.delenv("common_name", raising=False)
        monkeypatch.setenv("X509_0_CN", "vpn-user-x509")
        monkeypatch.setenv("untrusted_ip", "1.2.3.4")

        resp = MagicMock(status_code=200)
        resp.json.return_value = {"valid": True}
        client = MagicMock()
        client.post.return_value = resp

        assert handle_reneg(client, "token") == 0


# ---------------------------------------------------------------------------
# Management interface (kill by address)
# ---------------------------------------------------------------------------


class TestManagementSend:
    def test_sends_command_and_reads_success(self):
        sock = MagicMock()
        sock.recv.return_value = b"SUCCESS: common name 'vpn-user' found, 1 client(s) killed\r\n"
        result = _management_send(sock, "kill 1.2.3.4:36201")
        sock.sendall.assert_called_once_with(b"kill 1.2.3.4:36201\n")
        assert "SUCCESS" in result

    def test_sends_command_and_reads_error(self):
        sock = MagicMock()
        sock.recv.return_value = b"ERROR: address not found\r\n"
        result = _management_send(sock, "kill 1.2.3.4:99999")
        assert "ERROR" in result

    def test_reads_multipart_response_until_end(self):
        sock = MagicMock()
        sock.recv.side_effect = [
            b"HEADER,CLIENT_LIST,...\r\n",
            b"CLIENT_LIST,vpn-user,...\r\n\r\nEND\r\n",
        ]
        result = _management_send(sock, "status 2")
        assert "CLIENT_LIST" in result
        assert "END" in result


class TestKillClientViaManagement:
    def test_forks_background_process(self):
        with patch("scripts.openvpn.os.fork", return_value=12345) as mock_fork:
            _kill_client_via_management("1.2.3.4:36201")
            mock_fork.assert_called_once()

    def test_skips_empty_address(self):
        with patch("scripts.openvpn.os.fork") as mock_fork:
            _kill_client_via_management("")
            mock_fork.assert_not_called()

    def test_fork_failure_logs_warning(self):
        with patch("scripts.openvpn.os.fork", side_effect=OSError("fork failed")):
            # Should not raise
            _kill_client_via_management("1.2.3.4:36201")

    def test_child_kill_success(self):
        """Test child process kills by address successfully."""
        mock_sock = MagicMock()
        mock_sock.recv.side_effect = [
            b">INFO:OpenVPN Management Interface\r\n",
            b"SUCCESS: 1 client(s) killed\r\n",
        ]
        mock_sock.__enter__ = MagicMock(return_value=mock_sock)
        mock_sock.__exit__ = MagicMock(return_value=False)

        with (
            patch("scripts.openvpn.os.fork", return_value=0),
            patch("scripts.openvpn.os.setsid"),
            patch("scripts.openvpn.time.sleep"),
            patch("scripts.openvpn.socket.create_connection", return_value=mock_sock),
            patch("scripts.openvpn.os._exit") as mock_exit,
            patch("syslog.syslog"),
        ):
            _kill_client_via_management("1.2.3.4:36201")
            mock_sock.sendall.assert_any_call(b"kill 1.2.3.4:36201\n")
            mock_sock.sendall.assert_any_call(b"quit\n")
            mock_exit.assert_called_once_with(0)

    def test_child_exits_on_connection_error(self):
        """Test child exits cleanly when management connection fails."""
        with (
            patch("scripts.openvpn.os.fork", return_value=0),
            patch("scripts.openvpn.os.setsid"),
            patch("scripts.openvpn.time.sleep"),
            patch(
                "scripts.openvpn.socket.create_connection",
                side_effect=ConnectionRefusedError("refused"),
            ),
            patch("scripts.openvpn.os._exit") as mock_exit,
            patch("syslog.syslog"),
        ):
            _kill_client_via_management("1.2.3.4:36201")
            mock_exit.assert_called_once_with(0)


# ---------------------------------------------------------------------------
# main() / argparse
# ---------------------------------------------------------------------------


class TestMain:
    def test_connect_mode(self, monkeypatch):
        monkeypatch.setattr("sys.argv", ["openvpn.py", "--connect"])
        monkeypatch.setenv("common_name", "user")
        monkeypatch.setenv("untrusted_ip", "1.2.3.4")
        monkeypatch.setenv("ifconfig_pool_remote_ip", "10.8.0.6")

        validate = MagicMock(status_code=200)
        validate.json.return_value = {"valid": True, "routes": []}
        connect = MagicMock(status_code=200)

        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        # Token is cached, so only validate + connect API calls happen
        mock_client.post.side_effect = [validate, connect]

        with (
            patch("scripts.openvpn.httpx.Client", return_value=mock_client),
            patch("scripts.openvpn._load_cached_token", return_value="cached"),
        ):
            assert main() == 0

    def test_disconnect_mode(self, monkeypatch):
        monkeypatch.setattr("sys.argv", ["openvpn.py", "--disconnect"])
        monkeypatch.setenv("common_name", "user")
        monkeypatch.setenv("bytes_received", "100")
        monkeypatch.setenv("bytes_sent", "200")

        resp = MagicMock(status_code=200)
        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.post.return_value = resp

        with (
            patch("scripts.openvpn.httpx.Client", return_value=mock_client),
            patch("scripts.openvpn._load_cached_token", return_value="cached"),
        ):
            assert main() == 0

    def test_reneg_mode(self, monkeypatch):
        monkeypatch.setattr("sys.argv", ["openvpn.py", "--reneg", "1", "CN=CA"])

        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)

        with (
            patch("scripts.openvpn.httpx.Client", return_value=mock_client),
            patch("scripts.openvpn._load_cached_token", return_value="cached"),
        ):
            assert main() == 0

    def test_requires_mode_flag(self, monkeypatch):
        monkeypatch.setattr("sys.argv", ["openvpn.py"])

        with pytest.raises(SystemExit) as exc_info:
            main()
        assert exc_info.value.code == 2
