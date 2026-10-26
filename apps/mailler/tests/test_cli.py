# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for the ``mailler`` command line, run against a temporary SQLite database."""

import json
from unittest.mock import patch

import pytest
from mailler import cli
from mailler.models import AuthorizedClient, EmailTemplate
from sqlalchemy import select

MJML = "<mjml><mj-body><mj-section><mj-column><mj-text>Hello {{ name }}</mj-text></mj-column></mj-section></mj-body></mjml>"


@pytest.fixture
def run(sqlite_sessions, capsys):
    """Run the command line and return (exit code, stdout, stderr)."""

    def _run(*argv):
        with patch.object(cli, "get_sync_db", sqlite_sessions):
            code = cli.main(list(argv))
        captured = capsys.readouterr()
        return code, captured.out, captured.err

    return _run


@pytest.fixture
def database(sqlite_sessions):
    return sqlite_sessions


def _record(database, client_id="app-one"):
    with database() as db:
        return db.execute(
            select(AuthorizedClient).where(AuthorizedClient.client_id == client_id)
        ).scalar_one_or_none()


class TestRegister:
    def test_registers_a_client(self, run, database):
        code, out, _ = run(
            "clients",
            "register",
            "app-one",
            "--name",
            "Application one",
            "--from-email",
            "no-reply@app-one.example",
            "--from-name",
            "App One",
            "--reply-to",
            "support@app-one.example",
            "--allowed-sender",
            "alerts@app-one.example=Alerts",
            "--allowed-sender",
            "ops@app-one.example",
            "--allowed-provider",
            "brevo",
            "--allowed-provider",
            "ses",
            "--default-provider",
            "brevo",
            "--rate-limit-per-minute",
            "30",
            "--daily-quota",
            "1000",
        )
        assert code == 0
        assert "Registered client 'app-one'" in out
        record = _record(database)
        assert record.is_active is True
        assert record.from_email == "no-reply@app-one.example"
        assert record.allowed_senders == [
            {"email": "alerts@app-one.example", "name": "Alerts"},
            {"email": "ops@app-one.example", "name": None},
        ]
        assert record.allowed_providers == ["brevo", "ses"]
        assert (record.rate_limit_per_minute, record.daily_quota) == (30, 1000)

    def test_can_register_a_client_deactivated(self, run, database):
        assert run("clients", "register", "app-one", "--inactive")[0] == 0
        assert _record(database).is_active is False

    def test_twice_is_an_error(self, run):
        assert run("clients", "register", "app-one")[0] == 0
        code, _, err = run("clients", "register", "app-one")
        assert code == 1
        assert "already registered" in err

    def test_invalid_values_are_reported(self, run, database):
        code, _, err = run("clients", "register", "app-one", "--default-provider", "carrier")
        assert code == 2
        assert "Unknown provider" in err
        code, _, err = run("clients", "register", "app-one", "--from-email", "nope")
        assert code == 2
        assert _record(database) is None


class TestShowListUpdate:
    def test_show(self, run):
        run("clients", "register", "app-one", "--from-email", "a@one.example")
        code, out, _ = run("clients", "show", "app-one")
        assert code == 0
        data = json.loads(out)
        assert data["client_id"] == "app-one"
        assert data["from_email"] == "a@one.example"
        assert data["is_active"] is True

    def test_show_unknown(self, run):
        code, _, err = run("clients", "show", "nope")
        assert code == 1
        assert "not registered" in err

    def test_list(self, run):
        run("clients", "register", "b-app", "--default-provider", "brevo")
        run("clients", "register", "a-app", "--from-email", "a@a.example", "--inactive")
        code, out, _ = run("clients", "list")
        assert code == 0
        assert out.splitlines() == [
            "a-app\tinactive\ta@a.example\t-",
            "b-app\tactive\t-\tbrevo",
        ]

    def test_list_inactive(self, run):
        run("clients", "register", "b-app")
        run("clients", "register", "a-app", "--inactive")
        _, out, _ = run("clients", "list", "--inactive")
        assert out.split("\t")[0] == "a-app"
        assert "b-app" not in out

    def test_update_changes_only_the_given_fields(self, run, database):
        run("clients", "register", "app-one", "--from-email", "a@one.example", "--name", "One")
        code, out, _ = run(
            "clients", "update", "app-one", "--name", "Renamed", "--daily-quota", "5"
        )
        assert code == 0
        assert "Updated client 'app-one'" in out
        record = _record(database)
        assert (record.name, record.from_email, record.daily_quota) == (
            "Renamed",
            "a@one.example",
            5,
        )

    def test_update_can_clear_optional_fields(self, run, database):
        run(
            "clients",
            "register",
            "app-one",
            "--reply-to",
            "r@one.example",
            "--daily-quota",
            "5",
        )
        assert run("clients", "update", "app-one", "--reply-to", "", "--daily-quota", "0")[0] == 0
        record = _record(database)
        assert record.reply_to is None
        assert record.daily_quota is None

    def test_update_replaces_the_lists(self, run, database):
        run("clients", "register", "app-one", "--allowed-provider", "brevo")
        run("clients", "update", "app-one", "--allowed-provider", "ses")
        assert _record(database).allowed_providers == ["ses"]

    def test_update_without_options(self, run):
        run("clients", "register", "app-one")
        code, _, err = run("clients", "update", "app-one")
        assert code == 2
        assert "Nothing to update" in err

    def test_update_unknown_client(self, run):
        code, _, err = run("clients", "update", "nope", "--name", "x")
        assert code == 1
        assert "not registered" in err

    def test_update_validates(self, run):
        run("clients", "register", "app-one")
        code, _, err = run("clients", "update", "app-one", "--allowed-provider", "carrier")
        assert code == 2
        assert "Unknown provider" in err

    def test_deactivate_and_activate(self, run, database):
        run("clients", "register", "app-one")
        code, out, _ = run("clients", "deactivate", "app-one")
        assert code == 0
        assert "inactive" in out
        assert _record(database).is_active is False
        run("clients", "activate", "app-one")
        assert _record(database).is_active is True

    def test_activate_unknown_client(self, run):
        assert run("clients", "activate", "nope")[0] == 1


def _write(directory, slug, subject="Hello {{ name }}", mjml=MJML, **extra):
    (directory / f"{slug}.mjml").write_text(mjml)
    (directory / f"{slug}.json").write_text(json.dumps({"subject_template": subject, **extra}))


def _template(database, slug, client_id="app-one"):
    with database() as db:
        return db.execute(
            select(EmailTemplate).where(
                EmailTemplate.client_id == client_id, EmailTemplate.slug == slug
            )
        ).scalar_one_or_none()


class TestTemplatesImport:
    def test_imports_templates_as_active(self, run, database, tmp_path):
        _write(
            tmp_path, "workspace_invitation", name="Workspace invitation", plain_text="Hi %name%"
        )
        _write(tmp_path, "workspace_deleted")
        code, out, _ = run("templates", "import", "--client-id", "app-one", str(tmp_path))
        assert code == 0
        assert "Imported 2 template(s) for 'app-one': 2 new, 0 updated" in out
        template = _template(database, "workspace_invitation")
        assert template.status == "active"
        assert template.name == "Workspace invitation"
        assert template.subject_template == "Hello {{ name }}"
        assert template.plain_text == "Hi %name%"
        assert (
            "Hello {{name}}" in template.html_compiled
            or "Hello {{ name }}" in template.html_compiled
        )
        assert template.variables == ["name"]
        assert _template(database, "workspace_deleted").name == "workspace_deleted"

    def test_importing_again_updates(self, run, database, tmp_path):
        _write(tmp_path, "welcome", subject="First")
        run("templates", "import", "--client-id", "app-one", str(tmp_path))
        _write(tmp_path, "welcome", subject="Second")
        code, out, _ = run("templates", "import", "--client-id", "app-one", str(tmp_path))
        assert code == 0
        assert "0 new, 1 updated" in out
        assert _template(database, "welcome").subject_template == "Second"

    def test_templates_are_private_to_their_client(self, run, database, tmp_path):
        _write(tmp_path, "welcome")
        run("templates", "import", "--client-id", "app-one", str(tmp_path))
        run("templates", "import", "--client-id", "app-two", str(tmp_path))
        assert _template(database, "welcome", "app-one") is not None
        assert _template(database, "welcome", "app-two") is not None

    def test_status_option_and_description_status(self, run, database, tmp_path):
        _write(tmp_path, "one")
        _write(tmp_path, "two", status="archived")
        run("templates", "import", "--client-id", "app-one", "--status", "draft", str(tmp_path))
        assert _template(database, "one").status == "draft"
        assert _template(database, "two").status == "archived"

    def test_dry_run_writes_nothing(self, run, database, tmp_path):
        _write(tmp_path, "welcome")
        code, out, _ = run(
            "templates", "import", "--client-id", "app-one", "--dry-run", str(tmp_path)
        )
        assert code == 0
        assert out.startswith("Would import 1 template(s)")
        assert _template(database, "welcome") is None

    def test_one_invalid_template_stops_everything(self, run, database, tmp_path):
        _write(tmp_path, "good")
        _write(tmp_path, "bad", mjml="<mjml><mj-body><mj-nonsense/></mj-body></mjml>")
        with patch.object(cli, "compile_mjml", _fail_for):
            code, _, err = run("templates", "import", "--client-id", "app-one", str(tmp_path))
        assert code == 1
        assert "bad: MJML compilation failed" in err
        assert _template(database, "good") is None

    def test_files_are_checked(self, run, tmp_path):
        code, _, err = run("templates", "import", "--client-id", "app-one", str(tmp_path))
        assert code == 1
        assert "No .mjml file" in err

        (tmp_path / "lonely.mjml").write_text(MJML)
        code, _, err = run("templates", "import", "--client-id", "app-one", str(tmp_path))
        assert code == 1
        assert "missing lonely.json" in err

        (tmp_path / "lonely.json").write_text("{not json")
        code, _, err = run("templates", "import", "--client-id", "app-one", str(tmp_path))
        assert code == 1
        assert "invalid JSON" in err

        (tmp_path / "lonely.json").write_text("{}")
        code, _, err = run("templates", "import", "--client-id", "app-one", str(tmp_path))
        assert code == 2
        assert "subject_template" in err

        (tmp_path / "lonely.json").write_text('{"subject_template": "x", "unknown": 1}')
        code, _, err = run("templates", "import", "--client-id", "app-one", str(tmp_path))
        assert code == 2
        assert "unknown key(s) unknown" in err

        (tmp_path / "lonely.json").write_text('{"subject_template": "x", "status": "weird"}')
        code, _, err = run("templates", "import", "--client-id", "app-one", str(tmp_path))
        assert code == 1
        assert "unknown status" in err

    def test_slug_comes_from_the_file_name(self, run, tmp_path):
        _write(tmp_path, "Not A Slug")
        code, _, err = run("templates", "import", "--client-id", "app-one", str(tmp_path))
        assert code == 2
        assert "slug" in err

    def test_list(self, run, tmp_path):
        _write(tmp_path, "b_template", name="Second")
        _write(tmp_path, "a_template", name="First")
        run("templates", "import", "--client-id", "app-one", str(tmp_path))
        code, out, _ = run("templates", "list", "--client-id", "app-one")
        assert code == 0
        assert out.splitlines() == ["a_template\tactive\tFirst", "b_template\tactive\tSecond"]
        assert run("templates", "list", "--client-id", "other")[1] == ""


async def _fail_for(source):
    if "mj-nonsense" in source:
        return {"html": "", "errors": ["unknown tag"]}
    return {"html": "<p>{{ name }}</p>", "errors": None}


class TestParser:
    def test_a_command_is_required(self):
        with pytest.raises(SystemExit) as exc_info:
            cli.main([])
        assert exc_info.value.code == 2

    def test_unknown_status_is_refused(self):
        with pytest.raises(SystemExit) as exc_info:
            cli.main(["templates", "import", "--client-id", "x", "--status", "weird", "dir"])
        assert exc_info.value.code == 2


class TestConsoleScript:
    def test_the_mailler_command_runs_main(self):
        import tomllib
        from pathlib import Path

        pyproject = tomllib.loads((Path(cli.__file__).parents[2] / "pyproject.toml").read_text())
        assert pyproject["project"]["scripts"] == {"mailler": "mailler.cli:main"}


class TestRealCompilation:
    def test_broken_mjml_is_reported_by_the_compiler(self, run, database, tmp_path):
        _write(tmp_path, "good")
        _write(
            tmp_path,
            "bad",
            mjml="<mjml><mj-body><mj-section><mj-column><mj-text>x</mj-column></mj-section></mj-body></mjml>",
        )
        code, _, err = run("templates", "import", "--client-id", "app-one", str(tmp_path))
        assert code == 1
        assert "bad: MJML compilation failed" in err
        assert _template(database, "good") is None

    def test_jinja_statements_survive_the_compilation(self, run, database, tmp_path):
        mjml = (
            "<mjml><mj-body><mj-section><mj-column><mj-text>"
            "{% if name %}Hello {{ name }}{% else %}Hello{% endif %}"
            "</mj-text></mj-column></mj-section></mj-body></mjml>"
        )
        _write(tmp_path, "conditional", mjml=mjml)
        assert run("templates", "import", "--client-id", "app-one", str(tmp_path))[0] == 0
        compiled = _template(database, "conditional").html_compiled
        assert "{% if name %}" in compiled


class TestCallbacks:
    def test_a_callback_is_registered_from_a_secret_file(self, run, database, tmp_path):
        secret = tmp_path / "secret"
        secret.write_text("0123456789abcdef-secret\n")
        code, _, _ = run(
            "clients",
            "register",
            "app-one",
            "--callback-url",
            "https://app-one.example/hook",
            "--callback-secret-file",
            str(secret),
        )
        assert code == 0
        record = _record(database)
        assert record.callback_url == "https://app-one.example/hook"
        assert record.callback_secret == "0123456789abcdef-secret"

    def test_show_never_prints_the_secret(self, run, tmp_path):
        secret = tmp_path / "secret"
        secret.write_text("0123456789abcdef-secret")
        run(
            "clients",
            "register",
            "app-one",
            "--callback-url",
            "https://app-one.example/hook",
            "--callback-secret-file",
            str(secret),
        )
        _, out, _ = run("clients", "show", "app-one")
        data = json.loads(out)
        assert data["callback_url"] == "https://app-one.example/hook"
        assert data["has_callback_secret"] is True
        assert "0123456789abcdef-secret" not in out

    def test_a_url_needs_a_secret(self, run, database):
        code, _, err = run(
            "clients", "register", "app-one", "--callback-url", "https://a.example/h"
        )
        assert code == 2
        assert "callback_secret" in err
        assert _record(database) is None

    def test_http_urls_are_refused(self, run, tmp_path):
        secret = tmp_path / "secret"
        secret.write_text("0123456789abcdef-secret")
        code, _, err = run(
            "clients",
            "register",
            "app-one",
            "--callback-url",
            "http://a.example/h",
            "--callback-secret-file",
            str(secret),
        )
        assert code == 2
        assert "https" in err

    def test_an_unreadable_secret_file(self, run, tmp_path):
        code, _, err = run(
            "clients",
            "register",
            "app-one",
            "--callback-secret-file",
            str(tmp_path / "missing"),
        )
        assert code == 2
        assert "Cannot read" in err

    def test_update_checks_the_pair(self, run, database, tmp_path):
        run("clients", "register", "app-one")
        code, _, err = run("clients", "update", "app-one", "--callback-url", "https://a.example/h")
        assert code == 2
        assert "callback_secret" in err
        assert _record(database).callback_url is None

    def test_the_callback_can_be_removed(self, run, database, tmp_path):
        secret = tmp_path / "secret"
        secret.write_text("0123456789abcdef-secret")
        empty = tmp_path / "empty"
        empty.write_text("")
        run(
            "clients",
            "register",
            "app-one",
            "--callback-url",
            "https://a.example/h",
            "--callback-secret-file",
            str(secret),
        )
        code, _, _ = run(
            "clients",
            "update",
            "app-one",
            "--callback-url",
            "",
            "--callback-secret-file",
            str(empty),
        )
        assert code == 0
        record = _record(database)
        assert (record.callback_url, record.callback_secret) == (None, None)
