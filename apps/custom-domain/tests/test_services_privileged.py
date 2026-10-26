# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for custom_domain/services/privileged.py."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from custom_domain import privileged_helper
from custom_domain.config import ConfigurationError, settings
from custom_domain.services import privileged
from custom_domain.services.privileged import (
    PrivilegedResult,
    build_command,
    helper_arguments,
    run_privileged,
    stage_file,
    sudoers_lines,
)


def process_mock(returncode=0, stdout=b"", stderr=b""):
    process = AsyncMock()
    process.returncode = returncode
    process.communicate = AsyncMock(return_value=(stdout, stderr))
    return process


class TestBuildCommand:
    """The sudo command line is built from the settings."""

    def test_command_with_argument(self):
        argv = build_command("write-config", "shop.example.com")
        assert argv[:3] == ["sudo", "-n", "/opt/custom-domain/privileged-helper"]
        assert argv[3:] == [
            "--sites-dir",
            settings.nginx_sites_dir,
            "--config-prefix",
            "custom-domain-",
            "--staging-dir",
            settings.privileged_staging_dir,
            "write-config",
            "shop.example.com",
        ]

    def test_command_without_argument(self):
        assert build_command("test-nginx")[3:] == [
            "--nginx-bin",
            "/usr/sbin/nginx",
            "test-nginx",
        ]

    def test_unknown_command(self):
        with pytest.raises(KeyError):
            helper_arguments("format-disk")

    @pytest.mark.parametrize(
        ("setting", "command"),
        [
            ("privileged_helper", "test-nginx"),
            ("sudo_bin", "test-nginx"),
            ("nginx_bin", "test-nginx"),
            ("nginx_sites_dir", "remove-config"),
            ("privileged_staging_dir", "write-config"),
            ("systemctl_bin", "reload-nginx"),
        ],
    )
    def test_missing_setting_names_its_variable(self, monkeypatch, setting, command):
        monkeypatch.setattr(settings, setting, "")
        with pytest.raises(ConfigurationError, match=setting.upper()):
            build_command(command, "shop.example.com" if "config" in command else None)

    def test_every_command_is_accepted_by_the_helper(self):
        """What the application builds is exactly what the helper accepts."""
        for command, spec in privileged_helper.COMMANDS.items():
            argument = {"domain": "shop.example.com", "token": "a" * 32}.get(spec.argument or "")
            words = helper_arguments(command, argument)
            parsed, options, parsed_argument = privileged_helper.parse(words)
            assert parsed is spec
            assert set(options) == set(spec.options)
            assert parsed_argument == argument


class TestRunPrivileged:
    """Running a helper command."""

    @pytest.mark.asyncio
    async def test_success(self):
        with patch("asyncio.create_subprocess_exec", return_value=process_mock()) as mock_exec:
            result = await run_privileged("test-nginx")
        assert result.ok
        assert mock_exec.call_args[0] == tuple(build_command("test-nginx"))

    @pytest.mark.asyncio
    async def test_failure_carries_output(self):
        process = process_mock(returncode=64, stdout=b"out", stderr=b"invalid domain")
        with patch("asyncio.create_subprocess_exec", return_value=process):
            result = await run_privileged("remove-config", "bad")
        assert result == PrivilegedResult(returncode=64, stdout="out", stderr="invalid domain")
        assert not result.ok

    @pytest.mark.asyncio
    async def test_timeout_kills_the_process(self, monkeypatch):
        monkeypatch.setattr(settings, "privileged_timeout_seconds", 0.01)
        process = MagicMock()
        process.kill = MagicMock()
        process.wait = AsyncMock()

        async def hang():
            await asyncio.sleep(5)

        process.communicate = hang
        with (
            patch("asyncio.create_subprocess_exec", return_value=process),
            pytest.raises(TimeoutError),
        ):
            await run_privileged("test-nginx")
        process.kill.assert_called_once()

    @pytest.mark.asyncio
    async def test_unconfigured_helper_does_not_start_anything(self, monkeypatch):
        monkeypatch.setattr(settings, "privileged_helper", "")
        with (
            patch("asyncio.create_subprocess_exec") as mock_exec,
            pytest.raises(ConfigurationError),
        ):
            await run_privileged("test-nginx")
        mock_exec.assert_not_called()


class TestStageFile:
    """Staging files for the helper."""

    def test_writes_with_restricted_mode(self):
        path = stage_file("custom-domain-a.example.com.conf", "server {}")
        assert path.read_text() == "server {}"
        assert path.stat().st_mode & 0o777 == 0o640
        assert str(path.parent) == settings.privileged_staging_dir

    def test_overwrites(self):
        stage_file("x.conf", "first")
        assert stage_file("x.conf", "second").read_text() == "second"

    def test_requires_staging_dir(self, monkeypatch):
        monkeypatch.setattr(settings, "privileged_staging_dir", "")
        with pytest.raises(ConfigurationError, match="PRIVILEGED_STAGING_DIR"):
            stage_file("x.conf", "x")

    def test_refuses_to_follow_symlink(self, tmp_path):
        target = tmp_path / "target"
        target.write_text("keep")
        link = tmp_path / "staging" / "x.conf"
        link.symlink_to(target)
        with pytest.raises(OSError):
            stage_file("x.conf", "overwrite")
        assert target.read_text() == "keep"


class TestSudoersLines:
    """The sudoers rules are generated from the same table."""

    def test_one_rule_per_command(self):
        lines = sudoers_lines("worker")
        assert len(lines) == len(privileged_helper.COMMANDS)
        assert all(line.startswith("worker ALL=(root) NOPASSWD: ") for line in lines)

    def test_exact_lines(self):
        lines = sudoers_lines("worker")
        helper = "/opt/custom-domain/privileged-helper"
        sites, stage = settings.nginx_sites_dir, settings.privileged_staging_dir
        assert (
            f"worker ALL=(root) NOPASSWD: {helper} --sites-dir {sites} "
            f"--config-prefix custom-domain- --staging-dir {stage} write-config *"
        ) in lines
        assert (
            f"worker ALL=(root) NOPASSWD: {helper} --nginx-bin /usr/sbin/nginx test-nginx"
        ) in lines
        assert (
            f"worker ALL=(root) NOPASSWD: {helper} --systemctl-bin /usr/bin/systemctl "
            "--nginx-service nginx reload-nginx"
        ) in lines

    def test_arguments_are_a_wildcard_only_for_commands_that_take_one(self):
        for line, (command, spec) in zip(
            sudoers_lines("worker"), privileged_helper.COMMANDS.items(), strict=True
        ):
            assert f" {command}" in line
            assert line.endswith(" *") is (spec.argument is not None)

    def test_rules_match_the_commands_the_application_runs(self):
        for line, (command, spec) in zip(
            sudoers_lines("worker"), privileged_helper.COMMANDS.items(), strict=True
        ):
            rule = line.split("NOPASSWD: ", 1)[1]
            argument = "shop.example.com" if spec.argument else None
            actual = " ".join(build_command(command, argument)[2:])
            if spec.argument:
                assert actual.startswith(rule[:-1])
            else:
                assert actual == rule

    def test_special_characters_are_escaped(self, monkeypatch):
        monkeypatch.setattr(settings, "nginx_bin", "/opt/my nginx/bin,x=y")
        line = next(rule for rule in sudoers_lines("w") if "test-nginx" in rule)
        assert "--nginx-bin /opt/my\\ nginx/bin\\,x\\=y test-nginx" in line

    def test_requires_configuration(self, monkeypatch):
        monkeypatch.setattr(settings, "privileged_helper", "")
        with pytest.raises(ConfigurationError):
            sudoers_lines("worker")

    def test_main_prints_the_rules(self, capsys):
        privileged.main(["--user", "svc"])
        out = capsys.readouterr().out.splitlines()
        assert out == sudoers_lines("svc")
