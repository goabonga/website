# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for git operations tools."""

import sys
from unittest.mock import MagicMock, patch

import git
import pytest
import team.services.tools  # noqa: F401
from team.services.tool_service import ToolService


def _ctx(*, token="ghp_test", owner="myorg"):
    return {"agent_config": {"credentials": {"github_token": token, "github_owner": owner}}}


class TestGitClone:
    async def test_clone_success(self, tmp_path):
        ctx = _ctx()
        with (
            patch("team.services.tools.git_ops.get_settings") as m,
            patch("team.services.tools.git_ops._clone_sync") as mock_clone,
        ):
            m.return_value.workspace_dir = str(tmp_path)
            m.return_value.github_token = ""
            m.return_value.github_owner = ""

            result = await ToolService._registry["git_clone"][0](
                {"repo": "my-repo"},
                ctx,
            )
        assert result["cloned"] is True
        assert result["directory"] == "my-repo"
        mock_clone.assert_called_once()

    async def test_clone_with_branch_and_directory(self, tmp_path):
        ctx = _ctx()
        with (
            patch("team.services.tools.git_ops.get_settings") as m,
            patch("team.services.tools.git_ops._clone_sync") as mock_clone,
        ):
            m.return_value.workspace_dir = str(tmp_path)
            m.return_value.github_token = ""
            m.return_value.github_owner = ""

            result = await ToolService._registry["git_clone"][0](
                {"repo": "my-repo", "branch": "develop", "directory": "custom-dir"},
                ctx,
            )
        assert result["cloned"] is True
        assert result["directory"] == "custom-dir"
        call_args = mock_clone.call_args
        assert call_args[0][2] == "develop"

    async def test_clone_failure(self, tmp_path):
        ctx = _ctx()
        with (
            patch("team.services.tools.git_ops.get_settings") as m,
            patch("team.services.tools.git_ops._clone_sync") as mock_clone,
        ):
            m.return_value.workspace_dir = str(tmp_path)
            m.return_value.github_token = ""
            m.return_value.github_owner = ""
            mock_clone.side_effect = git.GitCommandError("clone", "fatal: repository not found")

            result = await ToolService._registry["git_clone"][0](
                {"repo": "nonexistent"},
                ctx,
            )
        assert "error" in result

    async def test_clone_redacts_token(self, tmp_path):
        ctx = _ctx(token="ghp_secret123")
        with (
            patch("team.services.tools.git_ops.get_settings") as m,
            patch("team.services.tools.git_ops._clone_sync") as mock_clone,
        ):
            m.return_value.workspace_dir = str(tmp_path)
            m.return_value.github_token = ""
            m.return_value.github_owner = ""
            mock_clone.side_effect = git.GitCommandError(
                "clone",
                "ghp_secret123 authentication failed",
            )

            result = await ToolService._registry["git_clone"][0](
                {"repo": "repo"},
                ctx,
            )
        assert "ghp_secret123" not in result["error"]
        assert "***" in result["error"]

    async def test_clone_no_credentials(self, tmp_path):
        ctx = _ctx(token="", owner="")
        with patch("team.services.tools.git_ops.get_settings") as m:
            m.return_value.workspace_dir = str(tmp_path)
            m.return_value.github_token = ""
            m.return_value.github_owner = ""
            result = await ToolService._registry["git_clone"][0](
                {"repo": "repo"},
                ctx,
            )
        assert "not configured" in result["error"]

    async def test_clone_path_traversal(self, tmp_path):
        ctx = _ctx()
        with patch("team.services.tools.git_ops.get_settings") as m:
            m.return_value.workspace_dir = str(tmp_path)
            m.return_value.github_token = ""
            m.return_value.github_owner = ""
            result = await ToolService._registry["git_clone"][0](
                {"repo": "repo", "directory": "../../evil"},
                ctx,
            )
        assert "error" in result
        assert "traversal" in result["error"].lower()

    async def test_clone_falls_back_to_global(self, tmp_path):
        ctx = {"agent_config": {"credentials": {}}}
        with (
            patch("team.services.tools.git_ops.get_settings") as m,
            patch("team.services.tools.git_ops._clone_sync"),
        ):
            m.return_value.workspace_dir = str(tmp_path)
            m.return_value.github_token = "ghp_global"
            m.return_value.github_owner = "global-org"

            result = await ToolService._registry["git_clone"][0](
                {"repo": "repo"},
                ctx,
            )
        assert result["cloned"] is True


class TestGitCommitPush:
    async def test_commit_push_success(self, tmp_path):
        repo_dir = tmp_path / "my-repo"
        repo_dir.mkdir()
        ctx = _ctx()

        with (
            patch("team.services.tools.git_ops.get_settings") as m,
            patch("team.services.tools.git_ops._commit_push_sync") as mock_push,
        ):
            m.return_value.workspace_dir = str(tmp_path)
            m.return_value.github_token = ""

            result = await ToolService._registry["git_commit_push"][0](
                {"directory": "my-repo", "message": "fix: bug"},
                ctx,
            )
        assert result["committed"] is True
        assert result["pushed"] is True
        mock_push.assert_called_once()

    async def test_commit_push_with_branch(self, tmp_path):
        repo_dir = tmp_path / "repo"
        repo_dir.mkdir()
        ctx = _ctx()

        with (
            patch("team.services.tools.git_ops.get_settings") as m,
            patch("team.services.tools.git_ops._commit_push_sync") as mock_push,
        ):
            m.return_value.workspace_dir = str(tmp_path)
            m.return_value.github_token = ""

            result = await ToolService._registry["git_commit_push"][0](
                {"directory": "repo", "message": "feat: new", "branch": "dev"},
                ctx,
            )
        assert result["committed"] is True
        call_args = mock_push.call_args
        assert call_args[0][2] == "dev"

    async def test_commit_push_git_error(self, tmp_path):
        repo_dir = tmp_path / "repo"
        repo_dir.mkdir()
        ctx = _ctx(token="ghp_secret")

        with (
            patch("team.services.tools.git_ops.get_settings") as m,
            patch("team.services.tools.git_ops._commit_push_sync") as mock_push,
        ):
            m.return_value.workspace_dir = str(tmp_path)
            m.return_value.github_token = ""
            mock_push.side_effect = git.GitCommandError(
                "push",
                "ghp_secret remote rejected",
            )

            result = await ToolService._registry["git_commit_push"][0](
                {"directory": "repo", "message": "test"},
                ctx,
            )
        assert "error" in result
        assert "ghp_secret" not in result["error"]

    async def test_commit_push_directory_not_found(self, tmp_path):
        ctx = _ctx()
        with patch("team.services.tools.git_ops.get_settings") as m:
            m.return_value.workspace_dir = str(tmp_path)
            m.return_value.github_token = ""
            result = await ToolService._registry["git_commit_push"][0](
                {"directory": "nonexistent", "message": "test"},
                ctx,
            )
        assert "not found" in result["error"].lower()

    async def test_commit_push_path_traversal(self, tmp_path):
        ctx = _ctx()
        with patch("team.services.tools.git_ops.get_settings") as m:
            m.return_value.workspace_dir = str(tmp_path)
            m.return_value.github_token = ""
            result = await ToolService._registry["git_commit_push"][0](
                {"directory": "../../evil", "message": "test"},
                ctx,
            )
        assert "traversal" in result["error"].lower()


class TestCloneSync:
    def test_clone_sync_without_branch(self):
        with patch.object(git.Repo, "clone_from") as mock_clone:
            from team.services.tools.git_ops import _clone_sync

            _clone_sync("https://github.com/org/repo.git", "/tmp/repo", None)
            mock_clone.assert_called_once_with(
                "https://github.com/org/repo.git",
                to_path="/tmp/repo",
            )

    def test_clone_sync_with_branch(self):
        with patch.object(git.Repo, "clone_from") as mock_clone:
            from team.services.tools.git_ops import _clone_sync

            _clone_sync("https://github.com/org/repo.git", "/tmp/repo", "dev")
            mock_clone.assert_called_once_with(
                "https://github.com/org/repo.git",
                to_path="/tmp/repo",
                branch="dev",
            )


class TestCommitPushSync:
    def test_commit_push_sync_without_branch(self):
        mock_repo = MagicMock(spec=git.Repo)
        mock_remote = MagicMock()
        mock_repo.remote.return_value = mock_remote

        with patch.object(git, "Repo", return_value=mock_repo):
            from team.services.tools.git_ops import _commit_push_sync

            _commit_push_sync("/tmp/repo", "commit msg", None)

        mock_repo.git.add.assert_called_once_with("-A")
        mock_repo.index.commit.assert_called_once_with("commit msg")
        mock_remote.push.assert_called_once_with()

    def test_commit_push_sync_with_branch(self):
        mock_repo = MagicMock(spec=git.Repo)
        mock_remote = MagicMock()
        mock_repo.remote.return_value = mock_remote

        with patch.object(git, "Repo", return_value=mock_repo):
            from team.services.tools.git_ops import _commit_push_sync

            _commit_push_sync("/tmp/repo", "commit msg", "feature")

        mock_remote.push.assert_called_once_with("feature")


class TestRequireGit:
    def test_raises_when_git_import_fails(self):
        from team.services.tools.git_ops import _require_git

        # Remove git from sys.modules so the import statement actually calls __import__
        saved = sys.modules.pop("git")
        try:
            with patch.dict("sys.modules", {}, clear=False):
                # Ensure 'git' is not in sys.modules
                sys.modules.pop("git", None)
                with (
                    patch("builtins.__import__", side_effect=ImportError("no git")),
                    pytest.raises(RuntimeError, match="not available"),
                ):
                    _require_git()
        finally:
            sys.modules["git"] = saved

    def test_raises_when_git_ok_is_false(self):
        from team.services.tools.git_ops import _require_git

        mock_git = MagicMock()
        mock_git.GIT_OK = False

        with (
            patch.dict("sys.modules", {"git": mock_git}),
            pytest.raises(RuntimeError, match="not found in .PATH"),
        ):
            _require_git()


class TestRedactToken:
    def test_redact_present_token(self):
        from team.services.tools.git_ops import _redact_token

        assert _redact_token("error ghp_abc123 failed", "ghp_abc123") == "error *** failed"

    def test_redact_empty_token(self):
        from team.services.tools.git_ops import _redact_token

        assert _redact_token("some error", "") == "some error"


class TestGitCreateBranch:
    async def test_create_branch_success(self, tmp_path):
        repo_dir = tmp_path / "my-repo"
        repo_dir.mkdir()
        ctx = _ctx()

        with (
            patch("team.services.tools.git_ops.get_settings") as m,
            patch(
                "team.services.tools.git_ops._create_branch_sync", return_value="feature/x"
            ) as mock_branch,
        ):
            m.return_value.workspace_dir = str(tmp_path)

            result = await ToolService._registry["git_create_branch"][0](
                {"directory": "my-repo", "branch": "feature/x"},
                ctx,
            )
        assert result["branch"] == "feature/x"
        assert result["directory"] == "my-repo"
        mock_branch.assert_called_once()
        assert mock_branch.call_args[0][1] == "feature/x"
        assert mock_branch.call_args[0][2] is None

    async def test_create_branch_with_base(self, tmp_path):
        repo_dir = tmp_path / "repo"
        repo_dir.mkdir()
        ctx = _ctx()

        with (
            patch("team.services.tools.git_ops.get_settings") as m,
            patch(
                "team.services.tools.git_ops._create_branch_sync", return_value="fix/bug"
            ) as mock_branch,
        ):
            m.return_value.workspace_dir = str(tmp_path)

            result = await ToolService._registry["git_create_branch"][0](
                {"directory": "repo", "branch": "fix/bug", "base": "develop"},
                ctx,
            )
        assert result["branch"] == "fix/bug"
        assert mock_branch.call_args[0][2] == "develop"

    async def test_create_branch_directory_not_found(self, tmp_path):
        ctx = _ctx()
        with patch("team.services.tools.git_ops.get_settings") as m:
            m.return_value.workspace_dir = str(tmp_path)
            result = await ToolService._registry["git_create_branch"][0](
                {"directory": "nonexistent", "branch": "feature"},
                ctx,
            )
        assert "not found" in result["error"].lower()

    async def test_create_branch_path_traversal(self, tmp_path):
        ctx = _ctx()
        with patch("team.services.tools.git_ops.get_settings") as m:
            m.return_value.workspace_dir = str(tmp_path)
            result = await ToolService._registry["git_create_branch"][0](
                {"directory": "../../evil", "branch": "feature"},
                ctx,
            )
        assert "traversal" in result["error"].lower()

    async def test_create_branch_git_error(self, tmp_path):
        repo_dir = tmp_path / "repo"
        repo_dir.mkdir()
        ctx = _ctx()

        with (
            patch("team.services.tools.git_ops.get_settings") as m,
            patch(
                "team.services.tools.git_ops._create_branch_sync",
                side_effect=git.GitCommandError("checkout", "already exists"),
            ),
        ):
            m.return_value.workspace_dir = str(tmp_path)
            result = await ToolService._registry["git_create_branch"][0](
                {"directory": "repo", "branch": "main"},
                ctx,
            )
        assert "error" in result


class TestGitDiff:
    async def test_diff_success(self, tmp_path):
        repo_dir = tmp_path / "repo"
        repo_dir.mkdir()
        ctx = _ctx()

        with (
            patch("team.services.tools.git_ops.get_settings") as m,
            patch(
                "team.services.tools.git_ops._diff_sync", return_value="=== Unstaged ===\n+new line"
            ) as mock_diff,
        ):
            m.return_value.workspace_dir = str(tmp_path)

            result = await ToolService._registry["git_diff"][0](
                {"directory": "repo"},
                ctx,
            )
        assert "Unstaged" in result["diff"]
        mock_diff.assert_called_once()

    async def test_diff_no_changes(self, tmp_path):
        repo_dir = tmp_path / "repo"
        repo_dir.mkdir()
        ctx = _ctx()

        with (
            patch("team.services.tools.git_ops.get_settings") as m,
            patch("team.services.tools.git_ops._diff_sync", return_value="(no changes)"),
        ):
            m.return_value.workspace_dir = str(tmp_path)

            result = await ToolService._registry["git_diff"][0](
                {"directory": "repo"},
                ctx,
            )
        assert result["diff"] == "(no changes)"

    async def test_diff_directory_not_found(self, tmp_path):
        ctx = _ctx()
        with patch("team.services.tools.git_ops.get_settings") as m:
            m.return_value.workspace_dir = str(tmp_path)
            result = await ToolService._registry["git_diff"][0](
                {"directory": "nonexistent"},
                ctx,
            )
        assert "not found" in result["error"].lower()

    async def test_diff_path_traversal(self, tmp_path):
        ctx = _ctx()
        with patch("team.services.tools.git_ops.get_settings") as m:
            m.return_value.workspace_dir = str(tmp_path)
            result = await ToolService._registry["git_diff"][0](
                {"directory": "../../evil"},
                ctx,
            )
        assert "traversal" in result["error"].lower()

    async def test_diff_git_error(self, tmp_path):
        repo_dir = tmp_path / "repo"
        repo_dir.mkdir()
        ctx = _ctx()

        with (
            patch("team.services.tools.git_ops.get_settings") as m,
            patch(
                "team.services.tools.git_ops._diff_sync",
                side_effect=git.GitCommandError("diff", "not a repo"),
            ),
        ):
            m.return_value.workspace_dir = str(tmp_path)
            result = await ToolService._registry["git_diff"][0](
                {"directory": "repo"},
                ctx,
            )
        assert "error" in result


class TestCreateBranchSync:
    def test_create_branch_without_base(self):
        mock_repo = MagicMock(spec=git.Repo)
        mock_repo.active_branch = "feature/new"

        with patch.object(git, "Repo", return_value=mock_repo):
            from team.services.tools.git_ops import _create_branch_sync

            result = _create_branch_sync("/tmp/repo", "feature/new", None)

        mock_repo.git.checkout.assert_called_once_with("-b", "feature/new")
        assert result == "feature/new"

    def test_create_branch_with_base(self):
        mock_repo = MagicMock(spec=git.Repo)
        mock_repo.active_branch = "fix/bug"

        with patch.object(git, "Repo", return_value=mock_repo):
            from team.services.tools.git_ops import _create_branch_sync

            result = _create_branch_sync("/tmp/repo", "fix/bug", "develop")

        # First checkout base, then create branch
        calls = mock_repo.git.checkout.call_args_list
        assert len(calls) == 2
        assert calls[0][0] == ("develop",)
        assert calls[1][0] == ("-b", "fix/bug")
        assert result == "fix/bug"


class TestDiffSync:
    def test_diff_with_both_staged_and_unstaged(self):
        mock_repo = MagicMock(spec=git.Repo)
        mock_repo.git.diff.side_effect = lambda *args: (
            "staged changes" if "--cached" in args else "unstaged changes"
        )

        with patch.object(git, "Repo", return_value=mock_repo):
            from team.services.tools.git_ops import _diff_sync

            result = _diff_sync("/tmp/repo")

        assert "Staged" in result
        assert "Unstaged" in result
        assert "staged changes" in result
        assert "unstaged changes" in result

    def test_diff_no_changes(self):
        mock_repo = MagicMock(spec=git.Repo)
        mock_repo.git.diff.return_value = ""

        with patch.object(git, "Repo", return_value=mock_repo):
            from team.services.tools.git_ops import _diff_sync

            result = _diff_sync("/tmp/repo")

        assert result == "(no changes)"

    def test_diff_only_staged(self):
        mock_repo = MagicMock(spec=git.Repo)
        mock_repo.git.diff.side_effect = lambda *args: "new file" if "--cached" in args else ""

        with patch.object(git, "Repo", return_value=mock_repo):
            from team.services.tools.git_ops import _diff_sync

            result = _diff_sync("/tmp/repo")

        assert "Staged" in result
        assert "Unstaged" not in result


class TestContextWorkspace:
    """Tests verifying git tools use workspace_dir from context when present."""

    async def test_clone_uses_context_workspace(self, tmp_path):
        ctx = {
            "agent_config": {"credentials": {"github_token": "ghp_t", "github_owner": "org"}},
            "workspace_dir": str(tmp_path),
        }
        with patch("team.services.tools.git_ops._clone_sync"):
            result = await ToolService._registry["git_clone"][0](
                {"repo": "my-repo"},
                ctx,
            )
        assert result["cloned"] is True

    async def test_commit_push_uses_context_workspace(self, tmp_path):
        repo_dir = tmp_path / "repo"
        repo_dir.mkdir()
        ctx = {
            "agent_config": {"credentials": {"github_token": "ghp_t", "github_owner": "org"}},
            "workspace_dir": str(tmp_path),
        }
        with patch("team.services.tools.git_ops._commit_push_sync"):
            result = await ToolService._registry["git_commit_push"][0](
                {"directory": "repo", "message": "test"},
                ctx,
            )
        assert result["committed"] is True

    async def test_create_branch_uses_context_workspace(self, tmp_path):
        repo_dir = tmp_path / "repo"
        repo_dir.mkdir()
        ctx = {
            "agent_config": {"credentials": {"github_token": "ghp_t", "github_owner": "org"}},
            "workspace_dir": str(tmp_path),
        }
        with patch("team.services.tools.git_ops._create_branch_sync", return_value="feat"):
            result = await ToolService._registry["git_create_branch"][0](
                {"directory": "repo", "branch": "feat"},
                ctx,
            )
        assert result["branch"] == "feat"

    async def test_diff_uses_context_workspace(self, tmp_path):
        repo_dir = tmp_path / "repo"
        repo_dir.mkdir()
        ctx = {
            "agent_config": {"credentials": {"github_token": "ghp_t", "github_owner": "org"}},
            "workspace_dir": str(tmp_path),
        }
        with patch("team.services.tools.git_ops._diff_sync", return_value="(no changes)"):
            result = await ToolService._registry["git_diff"][0](
                {"directory": "repo"},
                ctx,
            )
        assert result["diff"] == "(no changes)"

    async def test_context_workspace_path_traversal(self, tmp_path):
        ctx = {
            "agent_config": {"credentials": {"github_token": "ghp_t", "github_owner": "org"}},
            "workspace_dir": str(tmp_path),
        }
        result = await ToolService._registry["git_create_branch"][0](
            {"directory": "../../evil", "branch": "feat"},
            ctx,
        )
        assert "traversal" in result["error"].lower()
