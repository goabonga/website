# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for custom_domain/privileged_helper.py, run against fake binaries and temp dirs."""

import os
import stat
from pathlib import Path

import pytest
from custom_domain import privileged_helper as helper


def fake_binary(directory: Path, name: str, script: str) -> str:
    """Create an executable shell script and return its path."""
    path = directory / name
    path.write_text(f"#!/bin/sh\n{script}\n")
    path.chmod(0o755)
    return str(path)


@pytest.fixture
def dirs(tmp_path):
    """Sites and staging directories."""
    sites = tmp_path / "helper-sites"
    staging = tmp_path / "helper-staging"
    sites.mkdir()
    staging.mkdir()
    return sites, staging


def install_args(sites, staging, command="write-config", argument="shop.example.com"):
    return [
        "--sites-dir",
        str(sites),
        "--config-prefix",
        "custom-domain-",
        "--staging-dir",
        str(staging),
        command,
        argument,
    ]


class TestParse:
    """Command line validation."""

    @pytest.mark.parametrize("domain", ["a.example.com", "x-y.sub.example.org", "a1.io"])
    def test_accepts_domain(self, dirs, domain):
        sites, staging = dirs
        command, options, argument = helper.parse(install_args(sites, staging, argument=domain))
        assert argument == domain
        assert set(options) == set(command.options)

    @pytest.mark.parametrize(
        "domain",
        [
            "Example.com",
            "a.example.com;rm",
            "a b.example.com",
            "../etc/passwd",
            "-bad.example.com",
            "nodot",
            "a.example.com/x",
            "",
            "a" * 64 + ".example.com",
        ],
    )
    def test_rejects_domain(self, dirs, domain):
        sites, staging = dirs
        with pytest.raises(helper.UsageError):
            helper.parse(install_args(sites, staging, argument=domain))

    def test_rejects_unknown_command(self):
        with pytest.raises(helper.UsageError):
            helper.parse(["format-disk"])

    def test_rejects_missing_command(self):
        with pytest.raises(helper.UsageError):
            helper.parse([])

    def test_rejects_unknown_option(self, dirs):
        sites, staging = dirs
        with pytest.raises(helper.UsageError):
            helper.parse(["--shell", "/bin/sh", *install_args(sites, staging)])

    def test_rejects_extra_option(self, dirs):
        sites, staging = dirs
        args = ["--nginx-bin", "/bin/true", *install_args(sites, staging)]
        with pytest.raises(helper.UsageError, match="exactly the options"):
            helper.parse(args)

    def test_rejects_missing_option(self, dirs):
        sites, _ = dirs
        with pytest.raises(helper.UsageError, match="exactly the options"):
            helper.parse(["--sites-dir", str(sites), "write-config", "a.example.com"])

    def test_rejects_repeated_option(self, dirs):
        sites, staging = dirs
        args = ["--sites-dir", str(sites), *install_args(sites, staging)]
        with pytest.raises(helper.UsageError):
            helper.parse(args)

    def test_rejects_extra_argument(self, dirs):
        sites, staging = dirs
        with pytest.raises(helper.UsageError, match="argument"):
            helper.parse([*install_args(sites, staging), "other.example.com"])

    def test_rejects_argument_for_command_without_one(self):
        with pytest.raises(helper.UsageError, match="argument"):
            helper.parse(["--nginx-bin", "/bin/true", "test-nginx", "a.example.com"])

    @pytest.mark.parametrize("path", ["relative/dir", "/a/../b", "/a//b", "/a/./b", "/a\0b"])
    def test_rejects_unnormalized_paths(self, path):
        with pytest.raises(helper.UsageError):
            helper.parse(["--nginx-bin", path, "test-nginx"])

    def test_token_must_be_hex(self, dirs):
        _, staging = dirs
        base = ["--nginx-bin", "/bin/true", "--staging-dir", str(staging), "check-snippet"]
        assert helper.parse([*base, "a" * 32])[2] == "a" * 32
        for token in ("A" * 32, "a" * 31, "../" + "a" * 29, "a" * 33):
            with pytest.raises(helper.UsageError):
                helper.parse([*base, token])

    def test_prefix_is_validated(self, dirs):
        sites, staging = dirs
        args = install_args(sites, staging)
        args[3] = "../x"
        with pytest.raises(helper.UsageError):
            helper.parse(args)

    def test_every_command_option_has_a_validator(self):
        for command in helper.COMMANDS.values():
            assert set(command.options) <= set(helper.OPTIONS)


class TestWriteAndRemove:
    """Installing and removing virtual hosts."""

    def test_installs_staged_file(self, dirs):
        sites, staging = dirs
        (staging / "custom-domain-shop.example.com.conf").write_text("server { listen 80; }\n")
        assert helper.main(install_args(sites, staging)) == 0
        installed = sites / "custom-domain-shop.example.com.conf"
        assert installed.read_text() == "server { listen 80; }\n"
        assert stat.S_IMODE(installed.stat().st_mode) == 0o644
        assert [p.name for p in sites.iterdir()] == [installed.name]

    def test_replaces_existing_file(self, dirs):
        sites, staging = dirs
        (sites / "custom-domain-shop.example.com.conf").write_text("old")
        (staging / "custom-domain-shop.example.com.conf").write_text("new")
        assert helper.main(install_args(sites, staging)) == 0
        assert (sites / "custom-domain-shop.example.com.conf").read_text() == "new"

    def test_missing_staged_file_fails(self, dirs, capsys):
        sites, staging = dirs
        assert helper.main(install_args(sites, staging)) == 1
        assert list(sites.iterdir()) == []
        assert "custom-domain-privileged:" in capsys.readouterr().err

    def test_refuses_symlinked_staged_file(self, dirs, tmp_path):
        sites, staging = dirs
        secret = tmp_path / "secret"
        secret.write_text("root data")
        os.symlink(secret, staging / "custom-domain-shop.example.com.conf")
        assert helper.main(install_args(sites, staging)) == 1
        assert list(sites.iterdir()) == []

    def test_refuses_oversized_staged_file(self, dirs, monkeypatch):
        sites, staging = dirs
        monkeypatch.setattr(helper, "MAX_STAGED_BYTES", 4)
        (staging / "custom-domain-shop.example.com.conf").write_text("too large")
        assert helper.main(install_args(sites, staging)) == helper.EXIT_USAGE
        assert list(sites.iterdir()) == []

    def test_invalid_domain_touches_nothing(self, dirs, capsys):
        sites, staging = dirs
        assert helper.main(install_args(sites, staging, argument="a.example.com;x")) == 64
        assert "invalid domain" in capsys.readouterr().err
        assert list(sites.iterdir()) == []

    def test_removes_file(self, dirs):
        sites, staging = dirs
        target = sites / "custom-domain-shop.example.com.conf"
        target.write_text("x")
        other = sites / "custom-domain-other.example.com.conf"
        other.write_text("y")
        args = install_args(sites, staging, command="remove-config")
        args = args[:4] + args[6:]
        assert helper.main(args) == 0
        assert not target.exists()
        assert other.exists()

    def test_remove_is_idempotent(self, dirs):
        sites, _ = dirs
        args = ["--sites-dir", str(sites), "--config-prefix", "custom-domain-"]
        assert helper.main([*args, "remove-config", "gone.example.com"]) == 0


class TestNginxCommands:
    """nginx test, reload and snippet checks."""

    def test_check_nginx_runs_dash_t(self, tmp_path):
        out = tmp_path / "args"
        nginx = fake_binary(tmp_path, "nginx", f'echo "$@" > {out}')
        assert helper.main(["--nginx-bin", nginx, "test-nginx"]) == 0
        assert out.read_text().strip() == "-t"

    def test_check_nginx_propagates_failure(self, tmp_path, capfd):
        nginx = fake_binary(tmp_path, "nginx", "echo bad config >&2; exit 1")
        assert helper.main(["--nginx-bin", nginx, "test-nginx"]) == 1
        assert "bad config" in capfd.readouterr().err

    def test_reload_uses_configured_unit(self, tmp_path):
        out = tmp_path / "args"
        systemctl = fake_binary(tmp_path, "systemctl", f'echo "$@" > {out}')
        args = ["--systemctl-bin", systemctl, "--nginx-service", "edge.service", "reload-nginx"]
        assert helper.main(args) == 0
        assert out.read_text().strip() == "reload edge.service"

    def test_rejects_non_executable_binary(self, tmp_path, capsys):
        not_exec = tmp_path / "nginx"
        not_exec.write_text("x")
        assert helper.main(["--nginx-bin", str(not_exec), "test-nginx"]) == helper.EXIT_USAGE
        assert "not an executable" in capsys.readouterr().err

    def test_missing_binary_fails_cleanly(self, tmp_path, capsys):
        assert helper.main(["--nginx-bin", str(tmp_path / "absent"), "test-nginx"]) == 1
        assert "custom-domain-privileged:" in capsys.readouterr().err

    def test_check_snippet_wraps_staged_text(self, dirs, tmp_path):
        _, staging = dirs
        token = "0123456789abcdef0123456789abcdef"
        (staging / f"validate-{token}.conf").write_text("server { listen 80; }\n")
        out = tmp_path / "seen"
        nginx = fake_binary(
            tmp_path,
            "nginx",
            f'cat "$3" > {out}; cat "$(sed -n "s/.*include \\(.*\\);/\\1/p" "$3")" >> {out}',
        )
        args = ["--nginx-bin", nginx, "--staging-dir", str(staging), "check-snippet", token]
        assert helper.main(args) == 0
        seen = out.read_text()
        assert seen.startswith("events {}\nhttp {")
        assert "server { listen 80; }" in seen

    def test_check_snippet_reports_nginx_failure(self, dirs, tmp_path):
        _, staging = dirs
        token = "f" * 32
        (staging / f"validate-{token}.conf").write_text("broken")
        nginx = fake_binary(tmp_path, "nginx", "exit 1")
        args = ["--nginx-bin", nginx, "--staging-dir", str(staging), "check-snippet", token]
        assert helper.main(args) == 1

    def test_check_snippet_without_staged_file(self, dirs, tmp_path):
        _, staging = dirs
        nginx = fake_binary(tmp_path, "nginx", "exit 0")
        args = ["--nginx-bin", nginx, "--staging-dir", str(staging), "check-snippet", "e" * 32]
        assert helper.main(args) == 1


class TestEnvironment:
    """The child environment is reduced to a few variables."""

    def test_secrets_are_not_passed_on(self, tmp_path, monkeypatch):
        out = tmp_path / "env"
        monkeypatch.setenv("DATABASE_URL", "postgresql://secret")
        monkeypatch.setenv("PATH", "/usr/bin:/bin")
        nginx = fake_binary(tmp_path, "nginx", f"env > {out}")
        assert helper.main(["--nginx-bin", nginx, "test-nginx"]) == 0
        content = out.read_text()
        assert "DATABASE_URL" not in content
        assert "PATH=/usr/bin:/bin" in content
