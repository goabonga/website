# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for the certificate commands of custom_domain/privileged_helper.py."""

import pytest
from custom_domain import privileged_helper as helper

from tests.test_privileged_helper import fake_binary


@pytest.fixture
def recorder(tmp_path):
    """A fake certbot that records its arguments, one per line."""
    out = tmp_path / "certbot-args"
    binary = fake_binary(tmp_path, "certbot", f'for a in "$@"; do echo "$a"; done > {out}')
    return binary, out


class TestCertbotCommands:
    """certbot is run with exactly the expected arguments."""

    def test_issue(self, recorder, tmp_path):
        binary, out = recorder
        args = [
            "--certbot-bin",
            binary,
            "--webroot",
            "/srv/acme",
            "--email",
            "ops@example.invalid",
            "certbot-issue",
            "shop.example.com",
        ]
        assert helper.main(args) == 0
        assert out.read_text().split() == [
            "certonly",
            "--webroot",
            "--webroot-path",
            "/srv/acme",
            "-d",
            "shop.example.com",
            "--email",
            "ops@example.invalid",
            "--agree-tos",
            "--non-interactive",
            "--quiet",
        ]

    def test_issue_rejects_a_bad_email(self, recorder):
        binary, out = recorder
        args = [
            "--certbot-bin",
            binary,
            "--webroot",
            "/srv/acme",
            "--email",
            "ops@example.invalid --staging",
            "certbot-issue",
            "shop.example.com",
        ]
        assert helper.main(args) == helper.EXIT_USAGE
        assert not out.exists()

    def test_renew(self, recorder):
        binary, out = recorder
        assert helper.main(["--certbot-bin", binary, "certbot-renew", "shop.example.com"]) == 0
        assert out.read_text().split() == [
            "renew",
            "--cert-name",
            "shop.example.com",
            "--non-interactive",
            "--quiet",
        ]

    def test_failure_is_propagated(self, tmp_path, capfd):
        binary = fake_binary(tmp_path, "certbot", "echo rate limit >&2; exit 5")
        assert helper.main(["--certbot-bin", binary, "certbot-renew", "shop.example.com"]) == 5
        assert "rate limit" in capfd.readouterr().err

    def test_revoke_with_certificate(self, recorder, tmp_path):
        binary, out = recorder
        live = tmp_path / "le" / "live" / "shop.example.com"
        live.mkdir(parents=True)
        (live / "cert.pem").write_text("pem")
        args = [
            "--certbot-bin",
            binary,
            "--letsencrypt-dir",
            str(tmp_path / "le"),
            "certbot-revoke",
            "shop.example.com",
        ]
        assert helper.main(args) == 0
        assert out.read_text().split() == [
            "revoke",
            "--cert-path",
            str(live / "cert.pem"),
            "--delete-after-revoke",
            "--non-interactive",
            "--quiet",
        ]

    def test_revoke_without_certificate_succeeds(self, recorder, tmp_path, capsys):
        binary, out = recorder
        (tmp_path / "le").mkdir()
        args = [
            "--certbot-bin",
            binary,
            "--letsencrypt-dir",
            str(tmp_path / "le"),
            "certbot-revoke",
            "shop.example.com",
        ]
        assert helper.main(args) == 0
        assert "certificate absent" in capsys.readouterr().out
        assert not out.exists()


class TestCertDates:
    """The validity dates are read through openssl."""

    def test_prints_dates(self, tmp_path):
        live = tmp_path / "le" / "live" / "shop.example.com"
        live.mkdir(parents=True)
        (live / "fullchain.pem").write_text("pem")
        out = tmp_path / "openssl-args"
        openssl = fake_binary(
            tmp_path,
            "openssl",
            f'echo "$@" > {out}; echo notBefore=Jan  1 00:00:00 2024 GMT',
        )
        args = [
            "--openssl-bin",
            openssl,
            "--letsencrypt-dir",
            str(tmp_path / "le"),
            "cert-dates",
            "shop.example.com",
        ]
        assert helper.main(args) == 0
        assert out.read_text().split() == [
            "x509",
            "-in",
            str(live / "fullchain.pem"),
            "-noout",
            "-dates",
        ]

    def test_missing_certificate_has_its_own_status(self, tmp_path):
        (tmp_path / "le").mkdir()
        openssl = fake_binary(tmp_path, "openssl", "exit 0")
        args = [
            "--openssl-bin",
            openssl,
            "--letsencrypt-dir",
            str(tmp_path / "le"),
            "cert-dates",
            "shop.example.com",
        ]
        assert helper.main(args) == helper.EXIT_NOT_FOUND

    def test_a_domain_can_not_escape_the_certificate_directory(self, tmp_path):
        (tmp_path / "le").mkdir()
        openssl = fake_binary(tmp_path, "openssl", "exit 0")
        args = [
            "--openssl-bin",
            openssl,
            "--letsencrypt-dir",
            str(tmp_path / "le"),
            "cert-dates",
            "../../etc/passwd",
        ]
        assert helper.main(args) == helper.EXIT_USAGE
