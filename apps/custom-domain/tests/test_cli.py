# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Comprehensive tests for CLI commands (custom_domain/cli.py).

Tests all CLI commands using click.testing.CliRunner with mocked DB
interactions, targeting 100% coverage of cli.py.
"""

from unittest.mock import AsyncMock, MagicMock, patch

from click.testing import CliRunner
from custom_domain.cli import cli, get_async_url

# ============================================================
# get_async_url tests
# ============================================================


class TestGetAsyncUrl:
    """Tests for get_async_url() URL conversion."""

    @patch("custom_domain.cli.settings")
    def test_converts_postgresql_to_asyncpg(self, mock_settings):
        """Standard postgresql:// URL is converted to postgresql+asyncpg://."""
        mock_settings.database_url = "postgresql://user:pass@localhost:5432/mydb"
        result = get_async_url()
        assert result == "postgresql+asyncpg://user:pass@localhost:5432/mydb"

    @patch("custom_domain.cli.settings")
    def test_converts_unix_socket_url(self, mock_settings):
        """Unix socket format postgresql:///dbname is converted correctly."""
        mock_settings.database_url = "postgresql:///custom_domain"
        result = get_async_url()
        assert result == "postgresql+asyncpg:///custom_domain"

    @patch("custom_domain.cli.settings")
    def test_already_asyncpg_url_unchanged(self, mock_settings):
        """URL that does not start with postgresql:// is left as-is."""
        mock_settings.database_url = "sqlite:///test.db"
        result = get_async_url()
        assert result == "sqlite:///test.db"

    @patch("custom_domain.cli.settings")
    def test_url_with_host_and_port(self, mock_settings):
        """URL with explicit host/port is handled."""
        mock_settings.database_url = "postgresql://admin:secret@db.example.com:5433/prod"
        result = get_async_url()
        assert result == "postgresql+asyncpg://admin:secret@db.example.com:5433/prod"

    @patch("custom_domain.cli.settings")
    def test_url_with_both_patterns(self, mock_settings):
        """URL with postgresql:// is replaced (first match), not ///."""
        mock_settings.database_url = "postgresql://localhost/mydb"
        result = get_async_url()
        assert result == "postgresql+asyncpg://localhost/mydb"


# ============================================================
# CLI group tests
# ============================================================


class TestCliGroup:
    """Tests for the top-level CLI group."""

    def test_cli_group_help(self):
        """CLI --help exits cleanly and shows description."""
        runner = CliRunner()
        result = runner.invoke(cli, ["--help"])
        assert result.exit_code == 0
        assert "Custom Domain Service CLI" in result.output

    def test_cli_group_no_command(self):
        """Invoking CLI without subcommand shows usage (exit code 0 for groups with invoke_without_command)."""
        runner = CliRunner()
        result = runner.invoke(cli, [])
        # Click groups return exit code 0 if invoke_without_command is set, 2 otherwise
        assert "Usage:" in result.output or "Custom Domain Service CLI" in result.output


# ============================================================
# init-db command tests
# ============================================================


class TestInitDbCommand:
    """Tests for the init-db CLI command."""

    @patch("custom_domain.cli.asyncio.run")
    def test_init_db_invokes_asyncio_run(self, mock_asyncio_run):
        """init-db command calls asyncio.run with _init_db coroutine."""
        runner = CliRunner()
        result = runner.invoke(cli, ["init-db"])
        assert result.exit_code == 0
        mock_asyncio_run.assert_called_once()
        mock_asyncio_run.call_args[0][0].close()

    @patch("custom_domain.cli.create_async_engine")
    @patch("custom_domain.cli.get_async_url", return_value="postgresql+asyncpg:///test")
    def test_init_db_creates_tables(self, mock_get_url, mock_create_engine):
        """init-db creates all tables and disposes the engine."""
        import contextlib

        mock_conn = AsyncMock()
        mock_conn.run_sync = AsyncMock()

        mock_engine = MagicMock()

        @contextlib.asynccontextmanager
        async def fake_begin():
            yield mock_conn

        mock_engine.begin = fake_begin
        mock_engine.dispose = AsyncMock()
        mock_create_engine.return_value = mock_engine

        with patch(
            "custom_domain.cli.asyncio.run",
            side_effect=lambda coro: (
                __import__("asyncio")
                .get_event_loop_policy()
                .new_event_loop()
                .run_until_complete(coro)
            ),
        ):
            runner = CliRunner()
            result = runner.invoke(cli, ["init-db"])

        assert result.exit_code == 0
        assert "Database tables created successfully" in result.output
        mock_conn.run_sync.assert_called_once()
        mock_engine.dispose.assert_called_once()


# ============================================================
# seed command tests
# ============================================================


class TestSeedCommand:
    """Tests for the seed CLI command."""

    @patch("custom_domain.cli.asyncio.run")
    def test_seed_invokes_asyncio_run(self, mock_asyncio_run):
        """seed command calls asyncio.run."""
        runner = CliRunner()
        result = runner.invoke(cli, ["seed"])
        assert result.exit_code == 0
        mock_asyncio_run.assert_called_once()
        mock_asyncio_run.call_args[0][0].close()

    @patch("custom_domain.cli.get_session")
    def test_seed_default_template_already_exists(self, mock_get_session):
        """When default template exists, seed reports it and succeeds."""
        mock_session = AsyncMock()
        mock_get_session.return_value = mock_session

        mock_template = MagicMock()
        mock_template.name = "Existing Template"

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_template
        mock_session.execute = AsyncMock(return_value=mock_result)
        mock_session.close = AsyncMock()

        with patch(
            "custom_domain.cli.asyncio.run",
            side_effect=lambda coro: (
                __import__("asyncio")
                .get_event_loop_policy()
                .new_event_loop()
                .run_until_complete(coro)
            ),
        ):
            runner = CliRunner()
            result = runner.invoke(cli, ["seed"])

        assert result.exit_code == 0
        assert "Default template already exists: Existing Template" in result.output
        assert "Seed completed successfully" in result.output
        mock_session.close.assert_called_once()

    @patch("custom_domain.cli.Path")
    @patch("custom_domain.cli.get_session")
    def test_seed_creates_default_template(self, mock_get_session, mock_path_cls):
        """When no default template exists, seed creates one from files."""
        mock_session = AsyncMock()
        mock_get_session.return_value = mock_session

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute = AsyncMock(return_value=mock_result)
        mock_session.add = MagicMock()
        mock_session.commit = AsyncMock()
        mock_session.close = AsyncMock()

        # Mock template file paths
        mock_http_path = MagicMock()
        mock_http_path.exists.return_value = True
        mock_http_path.read_text.return_value = "server { listen 80; }"

        mock_https_path = MagicMock()
        mock_https_path.exists.return_value = True
        mock_https_path.read_text.return_value = "server { listen 443 ssl; }"

        mock_templates_dir = MagicMock()
        mock_templates_dir.__truediv__ = MagicMock(
            side_effect=lambda name: {
                "nginx_http.conf.j2": mock_http_path,
                "nginx_https.conf.j2": mock_https_path,
            }[name]
        )

        mock_parent = MagicMock()
        mock_parent.__truediv__ = MagicMock(return_value=mock_templates_dir)
        mock_path_instance = MagicMock()
        mock_path_instance.parent = mock_parent
        mock_path_cls.return_value = mock_path_instance

        with patch(
            "custom_domain.cli.asyncio.run",
            side_effect=lambda coro: (
                __import__("asyncio")
                .get_event_loop_policy()
                .new_event_loop()
                .run_until_complete(coro)
            ),
        ):
            runner = CliRunner()
            result = runner.invoke(cli, ["seed"])

        assert result.exit_code == 0
        assert "Created default nginx template" in result.output
        assert "Seed completed successfully" in result.output
        mock_session.add.assert_called_once()
        mock_session.commit.assert_called_once()
        mock_session.close.assert_called_once()

    @patch("custom_domain.cli.Path")
    @patch("custom_domain.cli.get_session")
    def test_seed_missing_http_template_file(self, mock_get_session, mock_path_cls):
        """Seed exits with error when HTTP template file is missing."""
        mock_session = AsyncMock()
        mock_get_session.return_value = mock_session

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute = AsyncMock(return_value=mock_result)
        mock_session.close = AsyncMock()

        # HTTP template does not exist
        mock_http_path = MagicMock()
        mock_http_path.exists.return_value = False

        mock_https_path = MagicMock()
        mock_https_path.exists.return_value = True

        mock_templates_dir = MagicMock()
        mock_templates_dir.__truediv__ = MagicMock(
            side_effect=lambda name: {
                "nginx_http.conf.j2": mock_http_path,
                "nginx_https.conf.j2": mock_https_path,
            }[name]
        )

        mock_parent = MagicMock()
        mock_parent.__truediv__ = MagicMock(return_value=mock_templates_dir)
        mock_path_instance = MagicMock()
        mock_path_instance.parent = mock_parent
        mock_path_cls.return_value = mock_path_instance

        with patch(
            "custom_domain.cli.asyncio.run",
            side_effect=lambda coro: (
                __import__("asyncio")
                .get_event_loop_policy()
                .new_event_loop()
                .run_until_complete(coro)
            ),
        ):
            runner = CliRunner()
            result = runner.invoke(cli, ["seed"])

        assert result.exit_code != 0
        assert "Error: Template files not found" in result.output

    @patch("custom_domain.cli.Path")
    @patch("custom_domain.cli.get_session")
    def test_seed_missing_https_template_file(self, mock_get_session, mock_path_cls):
        """Seed exits with error when HTTPS template file is missing."""
        mock_session = AsyncMock()
        mock_get_session.return_value = mock_session

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute = AsyncMock(return_value=mock_result)
        mock_session.close = AsyncMock()

        # HTTP exists but HTTPS does not
        mock_http_path = MagicMock()
        mock_http_path.exists.return_value = True

        mock_https_path = MagicMock()
        mock_https_path.exists.return_value = False

        mock_templates_dir = MagicMock()
        mock_templates_dir.__truediv__ = MagicMock(
            side_effect=lambda name: {
                "nginx_http.conf.j2": mock_http_path,
                "nginx_https.conf.j2": mock_https_path,
            }[name]
        )

        mock_parent = MagicMock()
        mock_parent.__truediv__ = MagicMock(return_value=mock_templates_dir)
        mock_path_instance = MagicMock()
        mock_path_instance.parent = mock_parent
        mock_path_cls.return_value = mock_path_instance

        with patch(
            "custom_domain.cli.asyncio.run",
            side_effect=lambda coro: (
                __import__("asyncio")
                .get_event_loop_policy()
                .new_event_loop()
                .run_until_complete(coro)
            ),
        ):
            runner = CliRunner()
            result = runner.invoke(cli, ["seed"])

        assert result.exit_code != 0
        assert "Error: Template files not found" in result.output

    @patch("custom_domain.cli.Path")
    @patch("custom_domain.cli.get_session")
    def test_seed_both_template_files_missing(self, mock_get_session, mock_path_cls):
        """Seed exits with error when both template files are missing."""
        mock_session = AsyncMock()
        mock_get_session.return_value = mock_session

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute = AsyncMock(return_value=mock_result)
        mock_session.close = AsyncMock()

        mock_http_path = MagicMock()
        mock_http_path.exists.return_value = False

        mock_https_path = MagicMock()
        mock_https_path.exists.return_value = False

        mock_templates_dir = MagicMock()
        mock_templates_dir.__truediv__ = MagicMock(
            side_effect=lambda name: {
                "nginx_http.conf.j2": mock_http_path,
                "nginx_https.conf.j2": mock_https_path,
            }[name]
        )

        mock_parent = MagicMock()
        mock_parent.__truediv__ = MagicMock(return_value=mock_templates_dir)
        mock_path_instance = MagicMock()
        mock_path_instance.parent = mock_parent
        mock_path_cls.return_value = mock_path_instance

        with patch(
            "custom_domain.cli.asyncio.run",
            side_effect=lambda coro: (
                __import__("asyncio")
                .get_event_loop_policy()
                .new_event_loop()
                .run_until_complete(coro)
            ),
        ):
            runner = CliRunner()
            result = runner.invoke(cli, ["seed"])

        assert result.exit_code != 0
        assert "Error: Template files not found" in result.output

    @patch("custom_domain.cli.get_session")
    def test_seed_database_error(self, mock_get_session):
        """Seed exits with error on unexpected database exception."""
        mock_session = AsyncMock()
        mock_get_session.return_value = mock_session

        mock_session.execute = AsyncMock(side_effect=Exception("connection refused"))
        mock_session.close = AsyncMock()

        with patch(
            "custom_domain.cli.asyncio.run",
            side_effect=lambda coro: (
                __import__("asyncio")
                .get_event_loop_policy()
                .new_event_loop()
                .run_until_complete(coro)
            ),
        ):
            runner = CliRunner()
            result = runner.invoke(cli, ["seed"])

        assert result.exit_code != 0
        assert "Error seeding database: connection refused" in result.output
        mock_session.close.assert_called_once()


# ============================================================
# create-client command tests
# ============================================================


class TestCreateClientCommand:
    """Tests for the create-client CLI command."""

    @patch("custom_domain.cli.asyncio.run")
    def test_create_client_invokes_asyncio_run(self, mock_asyncio_run):
        """create-client calls asyncio.run."""
        runner = CliRunner()
        result = runner.invoke(
            cli,
            ["create-client", "--client-id", "test", "--name", "Test"],
        )
        assert result.exit_code == 0
        mock_asyncio_run.assert_called_once()
        mock_asyncio_run.call_args[0][0].close()

    def test_create_client_missing_required_options(self):
        """create-client fails when required options are missing."""
        runner = CliRunner()
        # Missing --name
        result = runner.invoke(cli, ["create-client", "--client-id", "test"])
        assert result.exit_code != 0
        assert "Missing option" in result.output or "Error" in result.output

        # Missing --client-id
        result = runner.invoke(cli, ["create-client", "--name", "Test"])
        assert result.exit_code != 0

    @patch("custom_domain.cli.get_session")
    def test_create_client_success(self, mock_get_session):
        """create-client creates a new client with all options."""
        mock_session = AsyncMock()
        mock_get_session.return_value = mock_session

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute = AsyncMock(return_value=mock_result)
        mock_session.add = MagicMock()
        mock_session.commit = AsyncMock()
        mock_session.close = AsyncMock()

        with patch(
            "custom_domain.cli.asyncio.run",
            side_effect=lambda coro: (
                __import__("asyncio")
                .get_event_loop_policy()
                .new_event_loop()
                .run_until_complete(coro)
            ),
        ):
            runner = CliRunner()
            result = runner.invoke(
                cli,
                [
                    "create-client",
                    "--client-id",
                    "my-client",
                    "--name",
                    "My Client",
                    "--description",
                    "A test client",
                    "--upstream",
                    "localhost:8000",
                    "--cname",
                    "apps.example.com",
                    "--max-domains",
                    "10",
                ],
            )

        assert result.exit_code == 0
        assert "Created client: my-client" in result.output
        mock_session.add.assert_called_once()
        mock_session.commit.assert_called_once()
        mock_session.close.assert_called_once()

    @patch("custom_domain.cli.get_session")
    def test_create_client_minimal_options(self, mock_get_session):
        """create-client works with only required options (optional defaults to None)."""
        mock_session = AsyncMock()
        mock_get_session.return_value = mock_session

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute = AsyncMock(return_value=mock_result)
        mock_session.add = MagicMock()
        mock_session.commit = AsyncMock()
        mock_session.close = AsyncMock()

        with patch(
            "custom_domain.cli.asyncio.run",
            side_effect=lambda coro: (
                __import__("asyncio")
                .get_event_loop_policy()
                .new_event_loop()
                .run_until_complete(coro)
            ),
        ):
            runner = CliRunner()
            result = runner.invoke(
                cli,
                ["create-client", "--client-id", "minimal", "--name", "Minimal"],
            )

        assert result.exit_code == 0
        assert "Created client: minimal" in result.output
        mock_session.add.assert_called_once()
        mock_session.close.assert_called_once()

    @patch("custom_domain.cli.get_session")
    def test_create_client_already_exists(self, mock_get_session):
        """create-client exits with error when client already exists."""
        mock_session = AsyncMock()
        mock_get_session.return_value = mock_session

        existing_client = MagicMock()
        existing_client.client_id = "existing-client"

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = existing_client
        mock_session.execute = AsyncMock(return_value=mock_result)
        mock_session.close = AsyncMock()

        with patch(
            "custom_domain.cli.asyncio.run",
            side_effect=lambda coro: (
                __import__("asyncio")
                .get_event_loop_policy()
                .new_event_loop()
                .run_until_complete(coro)
            ),
        ):
            runner = CliRunner()
            result = runner.invoke(
                cli,
                [
                    "create-client",
                    "--client-id",
                    "existing-client",
                    "--name",
                    "Existing",
                ],
            )

        assert result.exit_code != 0
        assert "Client already exists: existing-client" in result.output
        mock_session.close.assert_called_once()

    @patch("custom_domain.cli.get_session")
    def test_create_client_database_error(self, mock_get_session):
        """create-client exits with error on database exception."""
        mock_session = AsyncMock()
        mock_get_session.return_value = mock_session

        mock_session.execute = AsyncMock(side_effect=Exception("db error"))
        mock_session.close = AsyncMock()

        with patch(
            "custom_domain.cli.asyncio.run",
            side_effect=lambda coro: (
                __import__("asyncio")
                .get_event_loop_policy()
                .new_event_loop()
                .run_until_complete(coro)
            ),
        ):
            runner = CliRunner()
            result = runner.invoke(
                cli,
                [
                    "create-client",
                    "--client-id",
                    "fail-client",
                    "--name",
                    "Fail",
                ],
            )

        assert result.exit_code != 0
        assert "Error creating client: db error" in result.output
        mock_session.close.assert_called_once()


# ============================================================
# list-clients command tests
# ============================================================


class TestListClientsCommand:
    """Tests for the list-clients CLI command."""

    @patch("custom_domain.cli.asyncio.run")
    def test_list_clients_invokes_asyncio_run(self, mock_asyncio_run):
        """list-clients calls asyncio.run."""
        runner = CliRunner()
        result = runner.invoke(cli, ["list-clients"])
        assert result.exit_code == 0
        mock_asyncio_run.assert_called_once()
        mock_asyncio_run.call_args[0][0].close()

    @patch("custom_domain.cli.get_session")
    def test_list_clients_no_clients(self, mock_get_session):
        """list-clients reports 'No clients found' when DB is empty."""
        mock_session = AsyncMock()
        mock_get_session.return_value = mock_session

        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = []
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute = AsyncMock(return_value=mock_result)
        mock_session.close = AsyncMock()

        with patch(
            "custom_domain.cli.asyncio.run",
            side_effect=lambda coro: (
                __import__("asyncio")
                .get_event_loop_policy()
                .new_event_loop()
                .run_until_complete(coro)
            ),
        ):
            runner = CliRunner()
            result = runner.invoke(cli, ["list-clients"])

        assert result.exit_code == 0
        assert "No clients found" in result.output
        mock_session.close.assert_called_once()

    @patch("custom_domain.cli.get_session")
    def test_list_clients_with_active_client(self, mock_get_session):
        """list-clients displays active client with all details."""
        mock_session = AsyncMock()
        mock_get_session.return_value = mock_session

        client = MagicMock()
        client.client_id = "my-client"
        client.name = "My Client"
        client.is_active = True
        client.default_upstream_target = "http://localhost:8000"
        client.default_cname_target = "apps.example.com"
        client.max_domains = 10

        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = [client]
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute = AsyncMock(return_value=mock_result)
        mock_session.close = AsyncMock()

        with patch(
            "custom_domain.cli.asyncio.run",
            side_effect=lambda coro: (
                __import__("asyncio")
                .get_event_loop_policy()
                .new_event_loop()
                .run_until_complete(coro)
            ),
        ):
            runner = CliRunner()
            result = runner.invoke(cli, ["list-clients"])

        assert result.exit_code == 0
        assert "Authorized Clients:" in result.output
        assert "my-client (My Client) - active" in result.output
        assert "Upstream: http://localhost:8000" in result.output
        assert "CNAME: apps.example.com" in result.output
        assert "Max domains: 10" in result.output
        mock_session.close.assert_called_once()

    @patch("custom_domain.cli.get_session")
    def test_list_clients_with_inactive_client(self, mock_get_session):
        """list-clients displays inactive client status."""
        mock_session = AsyncMock()
        mock_get_session.return_value = mock_session

        client = MagicMock()
        client.client_id = "inactive-client"
        client.name = "Inactive Client"
        client.is_active = False
        client.default_upstream_target = None
        client.default_cname_target = None
        client.max_domains = None

        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = [client]
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute = AsyncMock(return_value=mock_result)
        mock_session.close = AsyncMock()

        with patch(
            "custom_domain.cli.asyncio.run",
            side_effect=lambda coro: (
                __import__("asyncio")
                .get_event_loop_policy()
                .new_event_loop()
                .run_until_complete(coro)
            ),
        ):
            runner = CliRunner()
            result = runner.invoke(cli, ["list-clients"])

        assert result.exit_code == 0
        assert "inactive-client (Inactive Client) - inactive" in result.output
        # Optional fields should NOT appear
        assert "Upstream:" not in result.output
        assert "CNAME:" not in result.output
        assert "Max domains:" not in result.output
        mock_session.close.assert_called_once()

    @patch("custom_domain.cli.get_session")
    def test_list_clients_multiple_clients(self, mock_get_session):
        """list-clients displays multiple clients."""
        mock_session = AsyncMock()
        mock_get_session.return_value = mock_session

        client1 = MagicMock()
        client1.client_id = "client-a"
        client1.name = "Client A"
        client1.is_active = True
        client1.default_upstream_target = "http://a.local"
        client1.default_cname_target = None
        client1.max_domains = 5

        client2 = MagicMock()
        client2.client_id = "client-b"
        client2.name = "Client B"
        client2.is_active = False
        client2.default_upstream_target = None
        client2.default_cname_target = "b.example.com"
        client2.max_domains = None

        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = [client1, client2]
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute = AsyncMock(return_value=mock_result)
        mock_session.close = AsyncMock()

        with patch(
            "custom_domain.cli.asyncio.run",
            side_effect=lambda coro: (
                __import__("asyncio")
                .get_event_loop_policy()
                .new_event_loop()
                .run_until_complete(coro)
            ),
        ):
            runner = CliRunner()
            result = runner.invoke(cli, ["list-clients"])

        assert result.exit_code == 0
        assert "client-a (Client A) - active" in result.output
        assert "Upstream: http://a.local" in result.output
        assert "Max domains: 5" in result.output
        assert "client-b (Client B) - inactive" in result.output
        assert "CNAME: b.example.com" in result.output
        mock_session.close.assert_called_once()

    @patch("custom_domain.cli.get_session")
    def test_list_clients_with_upstream_only(self, mock_get_session):
        """list-clients shows upstream but no CNAME or max_domains."""
        mock_session = AsyncMock()
        mock_get_session.return_value = mock_session

        client = MagicMock()
        client.client_id = "up-only"
        client.name = "Upstream Only"
        client.is_active = True
        client.default_upstream_target = "http://upstream.local"
        client.default_cname_target = None
        client.max_domains = None

        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = [client]
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute = AsyncMock(return_value=mock_result)
        mock_session.close = AsyncMock()

        with patch(
            "custom_domain.cli.asyncio.run",
            side_effect=lambda coro: (
                __import__("asyncio")
                .get_event_loop_policy()
                .new_event_loop()
                .run_until_complete(coro)
            ),
        ):
            runner = CliRunner()
            result = runner.invoke(cli, ["list-clients"])

        assert result.exit_code == 0
        assert "Upstream: http://upstream.local" in result.output
        assert "CNAME:" not in result.output
        assert "Max domains:" not in result.output

    @patch("custom_domain.cli.get_session")
    def test_list_clients_with_cname_only(self, mock_get_session):
        """list-clients shows CNAME but no upstream or max_domains."""
        mock_session = AsyncMock()
        mock_get_session.return_value = mock_session

        client = MagicMock()
        client.client_id = "cname-only"
        client.name = "CNAME Only"
        client.is_active = True
        client.default_upstream_target = None
        client.default_cname_target = "cname.example.com"
        client.max_domains = None

        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = [client]
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute = AsyncMock(return_value=mock_result)
        mock_session.close = AsyncMock()

        with patch(
            "custom_domain.cli.asyncio.run",
            side_effect=lambda coro: (
                __import__("asyncio")
                .get_event_loop_policy()
                .new_event_loop()
                .run_until_complete(coro)
            ),
        ):
            runner = CliRunner()
            result = runner.invoke(cli, ["list-clients"])

        assert result.exit_code == 0
        assert "CNAME: cname.example.com" in result.output
        assert "Upstream:" not in result.output
        assert "Max domains:" not in result.output

    @patch("custom_domain.cli.get_session")
    def test_list_clients_with_max_domains_only(self, mock_get_session):
        """list-clients shows max_domains but no upstream or CNAME."""
        mock_session = AsyncMock()
        mock_get_session.return_value = mock_session

        client = MagicMock()
        client.client_id = "max-only"
        client.name = "Max Only"
        client.is_active = True
        client.default_upstream_target = None
        client.default_cname_target = None
        client.max_domains = 50

        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = [client]
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute = AsyncMock(return_value=mock_result)
        mock_session.close = AsyncMock()

        with patch(
            "custom_domain.cli.asyncio.run",
            side_effect=lambda coro: (
                __import__("asyncio")
                .get_event_loop_policy()
                .new_event_loop()
                .run_until_complete(coro)
            ),
        ):
            runner = CliRunner()
            result = runner.invoke(cli, ["list-clients"])

        assert result.exit_code == 0
        assert "Max domains: 50" in result.output
        assert "Upstream:" not in result.output
        assert "CNAME:" not in result.output

    @patch("custom_domain.cli.get_session")
    def test_list_clients_database_error(self, mock_get_session):
        """list-clients exits with error on database exception."""
        mock_session = AsyncMock()
        mock_get_session.return_value = mock_session

        mock_session.execute = AsyncMock(side_effect=Exception("timeout"))
        mock_session.close = AsyncMock()

        with patch(
            "custom_domain.cli.asyncio.run",
            side_effect=lambda coro: (
                __import__("asyncio")
                .get_event_loop_policy()
                .new_event_loop()
                .run_until_complete(coro)
            ),
        ):
            runner = CliRunner()
            result = runner.invoke(cli, ["list-clients"])

        assert result.exit_code != 0
        assert "Error listing clients: timeout" in result.output
        mock_session.close.assert_called_once()


# ============================================================
# list-templates command tests
# ============================================================


class TestListTemplatesCommand:
    """Tests for the list-templates CLI command."""

    @patch("custom_domain.cli.asyncio.run")
    def test_list_templates_invokes_asyncio_run(self, mock_asyncio_run):
        """list-templates calls asyncio.run."""
        runner = CliRunner()
        result = runner.invoke(cli, ["list-templates"])
        assert result.exit_code == 0
        mock_asyncio_run.assert_called_once()
        mock_asyncio_run.call_args[0][0].close()

    @patch("custom_domain.cli.get_session")
    def test_list_templates_no_templates(self, mock_get_session):
        """list-templates reports 'No templates found' when DB is empty."""
        mock_session = AsyncMock()
        mock_get_session.return_value = mock_session

        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = []
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute = AsyncMock(return_value=mock_result)
        mock_session.close = AsyncMock()

        with patch(
            "custom_domain.cli.asyncio.run",
            side_effect=lambda coro: (
                __import__("asyncio")
                .get_event_loop_policy()
                .new_event_loop()
                .run_until_complete(coro)
            ),
        ):
            runner = CliRunner()
            result = runner.invoke(cli, ["list-templates"])

        assert result.exit_code == 0
        assert "No templates found" in result.output
        mock_session.close.assert_called_once()

    @patch("custom_domain.cli.get_session")
    def test_list_templates_default_active_with_description(self, mock_get_session):
        """list-templates shows default active template with description."""
        mock_session = AsyncMock()
        mock_get_session.return_value = mock_session

        template = MagicMock()
        template.name = "Default Template"
        template.is_default = True
        template.is_active = True
        template.description = "Standard nginx proxy config"

        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = [template]
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute = AsyncMock(return_value=mock_result)
        mock_session.close = AsyncMock()

        with patch(
            "custom_domain.cli.asyncio.run",
            side_effect=lambda coro: (
                __import__("asyncio")
                .get_event_loop_policy()
                .new_event_loop()
                .run_until_complete(coro)
            ),
        ):
            runner = CliRunner()
            result = runner.invoke(cli, ["list-templates"])

        assert result.exit_code == 0
        assert "Nginx Templates:" in result.output
        assert "Default Template (DEFAULT) - active" in result.output
        assert "Standard nginx proxy config" in result.output
        mock_session.close.assert_called_once()

    @patch("custom_domain.cli.get_session")
    def test_list_templates_non_default_inactive_no_description(self, mock_get_session):
        """list-templates shows non-default inactive template without description."""
        mock_session = AsyncMock()
        mock_get_session.return_value = mock_session

        template = MagicMock()
        template.name = "Custom Template"
        template.is_default = False
        template.is_active = False
        template.description = None

        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = [template]
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute = AsyncMock(return_value=mock_result)
        mock_session.close = AsyncMock()

        with patch(
            "custom_domain.cli.asyncio.run",
            side_effect=lambda coro: (
                __import__("asyncio")
                .get_event_loop_policy()
                .new_event_loop()
                .run_until_complete(coro)
            ),
        ):
            runner = CliRunner()
            result = runner.invoke(cli, ["list-templates"])

        assert result.exit_code == 0
        assert "Custom Template - inactive" in result.output
        # Should NOT include "(DEFAULT)" marker
        assert "(DEFAULT)" not in result.output
        mock_session.close.assert_called_once()

    @patch("custom_domain.cli.get_session")
    def test_list_templates_multiple_templates(self, mock_get_session):
        """list-templates displays multiple templates correctly."""
        mock_session = AsyncMock()
        mock_get_session.return_value = mock_session

        t1 = MagicMock()
        t1.name = "Default"
        t1.is_default = True
        t1.is_active = True
        t1.description = "The default template"

        t2 = MagicMock()
        t2.name = "SPA"
        t2.is_default = False
        t2.is_active = True
        t2.description = "Single page app template"

        t3 = MagicMock()
        t3.name = "Legacy"
        t3.is_default = False
        t3.is_active = False
        t3.description = None

        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = [t1, t2, t3]
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute = AsyncMock(return_value=mock_result)
        mock_session.close = AsyncMock()

        with patch(
            "custom_domain.cli.asyncio.run",
            side_effect=lambda coro: (
                __import__("asyncio")
                .get_event_loop_policy()
                .new_event_loop()
                .run_until_complete(coro)
            ),
        ):
            runner = CliRunner()
            result = runner.invoke(cli, ["list-templates"])

        assert result.exit_code == 0
        assert "Default (DEFAULT) - active" in result.output
        assert "The default template" in result.output
        assert "SPA - active" in result.output
        assert "Single page app template" in result.output
        assert "Legacy - inactive" in result.output
        mock_session.close.assert_called_once()

    @patch("custom_domain.cli.get_session")
    def test_list_templates_active_non_default_with_description(self, mock_get_session):
        """list-templates shows active non-default template with description."""
        mock_session = AsyncMock()
        mock_get_session.return_value = mock_session

        template = MagicMock()
        template.name = "Reverse Proxy"
        template.is_default = False
        template.is_active = True
        template.description = "Advanced reverse proxy config"

        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = [template]
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute = AsyncMock(return_value=mock_result)
        mock_session.close = AsyncMock()

        with patch(
            "custom_domain.cli.asyncio.run",
            side_effect=lambda coro: (
                __import__("asyncio")
                .get_event_loop_policy()
                .new_event_loop()
                .run_until_complete(coro)
            ),
        ):
            runner = CliRunner()
            result = runner.invoke(cli, ["list-templates"])

        assert result.exit_code == 0
        assert "Reverse Proxy - active" in result.output
        assert "Advanced reverse proxy config" in result.output
        assert "(DEFAULT)" not in result.output

    @patch("custom_domain.cli.get_session")
    def test_list_templates_database_error(self, mock_get_session):
        """list-templates exits with error on database exception."""
        mock_session = AsyncMock()
        mock_get_session.return_value = mock_session

        mock_session.execute = AsyncMock(side_effect=Exception("connection lost"))
        mock_session.close = AsyncMock()

        with patch(
            "custom_domain.cli.asyncio.run",
            side_effect=lambda coro: (
                __import__("asyncio")
                .get_event_loop_policy()
                .new_event_loop()
                .run_until_complete(coro)
            ),
        ):
            runner = CliRunner()
            result = runner.invoke(cli, ["list-templates"])

        assert result.exit_code != 0
        assert "Error listing templates: connection lost" in result.output
        mock_session.close.assert_called_once()


# ============================================================
# get_session tests
# ============================================================


class TestGetSession:
    """Tests for the get_session() async function."""

    @patch("custom_domain.cli.async_sessionmaker")
    @patch("custom_domain.cli.create_async_engine")
    @patch("custom_domain.cli.get_async_url", return_value="postgresql+asyncpg:///test")
    def test_get_session_returns_session(self, mock_url, mock_engine_cls, mock_sessionmaker):
        """get_session creates engine, sessionmaker, and returns a session."""
        import asyncio

        mock_engine = MagicMock()
        mock_engine_cls.return_value = mock_engine

        mock_session = AsyncMock()
        mock_factory = MagicMock(return_value=mock_session)
        mock_sessionmaker.return_value = mock_factory

        from custom_domain.cli import get_session

        loop = asyncio.new_event_loop()
        try:
            result = loop.run_until_complete(get_session())
        finally:
            loop.close()

        mock_engine_cls.assert_called_once_with("postgresql+asyncpg:///test")
        mock_sessionmaker.assert_called_once()
        assert result == mock_session


# ============================================================
# Command help text tests
# ============================================================


class TestCommandHelp:
    """Tests for command help text output."""

    def test_init_db_help(self):
        """init-db --help shows usage information."""
        runner = CliRunner()
        result = runner.invoke(cli, ["init-db", "--help"])
        assert result.exit_code == 0
        assert "Create all database tables" in result.output

    def test_seed_help(self):
        """seed --help shows usage information."""
        runner = CliRunner()
        result = runner.invoke(cli, ["seed", "--help"])
        assert result.exit_code == 0
        assert "Seed the database" in result.output

    def test_create_client_help(self):
        """create-client --help shows all options."""
        runner = CliRunner()
        result = runner.invoke(cli, ["create-client", "--help"])
        assert result.exit_code == 0
        assert "--client-id" in result.output
        assert "--name" in result.output
        assert "--description" in result.output
        assert "--upstream" in result.output
        assert "--cname" in result.output
        assert "--max-domains" in result.output

    def test_list_clients_help(self):
        """list-clients --help shows usage information."""
        runner = CliRunner()
        result = runner.invoke(cli, ["list-clients", "--help"])
        assert result.exit_code == 0
        assert "List all authorized clients" in result.output

    def test_list_templates_help(self):
        """list-templates --help shows usage information."""
        runner = CliRunner()
        result = runner.invoke(cli, ["list-templates", "--help"])
        assert result.exit_code == 0
        assert "List all nginx templates" in result.output


# ============================================================
# Edge case: separator line in list outputs
# ============================================================


class TestListOutputFormatting:
    """Tests for output formatting details in list commands."""

    @patch("custom_domain.cli.get_session")
    def test_list_clients_shows_separator(self, mock_get_session):
        """list-clients output includes separator line."""
        mock_session = AsyncMock()
        mock_get_session.return_value = mock_session

        client = MagicMock()
        client.client_id = "fmt-test"
        client.name = "Format Test"
        client.is_active = True
        client.default_upstream_target = None
        client.default_cname_target = None
        client.max_domains = None

        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = [client]
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute = AsyncMock(return_value=mock_result)
        mock_session.close = AsyncMock()

        with patch(
            "custom_domain.cli.asyncio.run",
            side_effect=lambda coro: (
                __import__("asyncio")
                .get_event_loop_policy()
                .new_event_loop()
                .run_until_complete(coro)
            ),
        ):
            runner = CliRunner()
            result = runner.invoke(cli, ["list-clients"])

        assert result.exit_code == 0
        assert "-" * 60 in result.output

    @patch("custom_domain.cli.get_session")
    def test_list_templates_shows_separator(self, mock_get_session):
        """list-templates output includes separator line."""
        mock_session = AsyncMock()
        mock_get_session.return_value = mock_session

        template = MagicMock()
        template.name = "Sep Test"
        template.is_default = False
        template.is_active = True
        template.description = None

        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = [template]
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute = AsyncMock(return_value=mock_result)
        mock_session.close = AsyncMock()

        with patch(
            "custom_domain.cli.asyncio.run",
            side_effect=lambda coro: (
                __import__("asyncio")
                .get_event_loop_policy()
                .new_event_loop()
                .run_until_complete(coro)
            ),
        ):
            runner = CliRunner()
            result = runner.invoke(cli, ["list-templates"])

        assert result.exit_code == 0
        assert "-" * 60 in result.output


class TestCreateSchema:
    """The enum type must exist before the tables that use it are created."""

    def test_enum_is_created_before_the_tables(self):
        """_create_schema creates the domainstatus enum first and then all tables."""
        from unittest.mock import MagicMock, patch

        from custom_domain.cli import _create_schema
        from custom_domain.models import Base

        order = MagicMock()
        connection = MagicMock()
        with (
            patch("custom_domain.cli.postgresql.ENUM") as enum_cls,
            patch.object(Base.metadata, "create_all") as create_all,
        ):
            order.attach_mock(enum_cls.return_value.create, "create_enum")
            order.attach_mock(create_all, "create_all")
            _create_schema(connection)

        assert [call[0] for call in order.mock_calls] == ["create_enum", "create_all"]
        names = enum_cls.call_args.args
        assert "pending" in names and "active" in names
        assert enum_cls.call_args.kwargs == {"name": "domainstatus"}
        order.create_enum.assert_called_once_with(connection, checkfirst=True)


# ============================================================
# sudoers command tests
# ============================================================


class TestSudoersCommand:
    """Tests for the sudoers command."""

    def test_prints_one_rule_per_helper_command(self):
        """The rules are the ones the service module generates."""
        from custom_domain import privileged_helper
        from custom_domain.services.privileged import sudoers_lines

        result = CliRunner().invoke(cli, ["sudoers", "--user", "worker"])

        assert result.exit_code == 0
        assert result.output.splitlines() == sudoers_lines("worker")
        assert len(result.output.splitlines()) == len(privileged_helper.COMMANDS)

    def test_user_is_required(self):
        result = CliRunner().invoke(cli, ["sudoers"])
        assert result.exit_code == 2
        assert "--user" in result.output

    def test_unconfigured_deployment_is_reported(self, monkeypatch):
        from custom_domain.config import settings

        monkeypatch.setattr(settings, "privileged_helper", "")
        result = CliRunner().invoke(cli, ["sudoers", "--user", "worker"])
        assert result.exit_code == 1
        assert "PRIVILEGED_HELPER is not configured" in result.output
