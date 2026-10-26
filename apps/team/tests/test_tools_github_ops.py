# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for GitHub operations tools."""

from unittest.mock import AsyncMock, MagicMock, patch

import team.services.tools  # noqa: F401
from team.services.tool_service import ToolService


def _mock_context(*, token="ghp_test", owner="myorg"):
    """Build a context dict with mocked tool_service and agent config."""
    service = ToolService()
    mock_client = AsyncMock()
    service._client = mock_client
    return {
        "tool_service": service,
        "agent_config": {"credentials": {"github_token": token, "github_owner": owner}},
    }, mock_client


def _github_response(status_code, json_data=None, text=""):
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = json_data or {}
    resp.text = text
    return resp


class TestNormalizeRepo:
    def test_plain_repo_name(self):
        from team.services.tools.github_ops import _normalize_repo

        assert _normalize_repo("knowledge", "goabonga") == ("goabonga", "knowledge")

    def test_owner_slash_repo(self):
        from team.services.tools.github_ops import _normalize_repo

        assert _normalize_repo("other-org/knowledge", "goabonga") == ("other-org", "knowledge")

    def test_owner_override(self):
        from team.services.tools.github_ops import _normalize_repo

        owner, repo = _normalize_repo("alice/myrepo", "default-owner")
        assert owner == "alice"
        assert repo == "myrepo"


class TestGitHubGetIssueWithOwnerRepo:
    async def test_owner_repo_format_resolves_correctly(self):
        ctx, client = _mock_context()
        client.get = AsyncMock(
            return_value=_github_response(
                200,
                {
                    "number": 1,
                    "title": "Test",
                    "body": "",
                    "state": "open",
                    "labels": [],
                    "assignees": [],
                    "comments": 0,
                    "html_url": "https://github.com/other/repo/issues/1",
                    "created_at": "2026-02-01T00:00:00Z",
                    "updated_at": "2026-02-01T00:00:00Z",
                },
            )
        )
        result = await ToolService._registry["github_get_issue"][0](
            {"repo": "other-org/knowledge", "issue_number": 1},
            ctx,
        )
        assert result["issue_number"] == 1
        url = client.get.call_args[0][0]
        assert "/repos/other-org/knowledge/issues/1" in url


class TestGitHubCreateIssue:
    async def test_create_issue_success(self):
        ctx, client = _mock_context()
        client.post = AsyncMock(
            return_value=_github_response(
                201,
                {
                    "number": 42,
                    "html_url": "https://github.com/myorg/repo/issues/42",
                },
            )
        )
        result = await ToolService._registry["github_create_issue"][0](
            {"repo": "repo", "title": "Bug"},
            ctx,
        )
        assert result["issue_number"] == 42
        assert "url" in result

    async def test_create_issue_with_body_and_labels(self):
        ctx, client = _mock_context()
        client.post = AsyncMock(
            return_value=_github_response(
                201,
                {
                    "number": 1,
                    "html_url": "https://github.com/myorg/repo/issues/1",
                },
            )
        )
        result = await ToolService._registry["github_create_issue"][0](
            {"repo": "repo", "title": "Feature", "body": "Details", "labels": ["enhancement"]},
            ctx,
        )
        assert result["issue_number"] == 1
        payload = client.post.call_args[1]["json"]
        assert payload["body"] == "Details"
        assert payload["labels"] == ["enhancement"]

    async def test_create_issue_api_error(self):
        ctx, client = _mock_context()
        client.post = AsyncMock(return_value=_github_response(422, text="Validation Failed"))
        result = await ToolService._registry["github_create_issue"][0](
            {"repo": "repo", "title": "Bug"},
            ctx,
        )
        assert "error" in result
        assert "422" in result["error"]

    async def test_create_issue_no_token(self):
        ctx, _ = _mock_context(token="", owner="myorg")
        result = await ToolService._registry["github_create_issue"][0](
            {"repo": "repo", "title": "Bug"},
            ctx,
        )
        assert result["error"] == "GitHub token or owner not configured"

    async def test_create_issue_no_owner(self):
        ctx, _ = _mock_context(token="ghp_test", owner="")
        result = await ToolService._registry["github_create_issue"][0](
            {"repo": "repo", "title": "Bug"},
            ctx,
        )
        assert result["error"] == "GitHub token or owner not configured"

    async def test_create_issue_falls_back_to_global_settings(self):
        service = ToolService()
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(
            return_value=_github_response(
                201,
                {
                    "number": 5,
                    "html_url": "https://github.com/global-org/repo/issues/5",
                },
            )
        )
        service._client = mock_client

        ctx = {"tool_service": service, "agent_config": {"credentials": {}}}
        with patch("team.services.tools.github_ops.get_settings") as mock_settings:
            mock_settings.return_value.github_token = "ghp_global"
            mock_settings.return_value.github_owner = "global-org"
            result = await ToolService._registry["github_create_issue"][0](
                {"repo": "repo", "title": "Bug"},
                ctx,
            )
        assert result["issue_number"] == 5


class TestGitHubCreatePr:
    async def test_create_pr_success(self):
        ctx, client = _mock_context()
        client.post = AsyncMock(
            return_value=_github_response(
                201,
                {
                    "number": 10,
                    "html_url": "https://github.com/myorg/repo/pull/10",
                },
            )
        )
        result = await ToolService._registry["github_create_pr"][0](
            {"repo": "repo", "title": "Feature", "head": "feature-branch"},
            ctx,
        )
        assert result["pr_number"] == 10

    async def test_create_pr_with_body_and_base(self):
        ctx, client = _mock_context()
        client.post = AsyncMock(
            return_value=_github_response(
                201,
                {
                    "number": 11,
                    "html_url": "https://github.com/myorg/repo/pull/11",
                },
            )
        )
        result = await ToolService._registry["github_create_pr"][0](
            {"repo": "repo", "title": "PR", "head": "dev", "base": "develop", "body": "PR body"},
            ctx,
        )
        assert result["pr_number"] == 11
        payload = client.post.call_args[1]["json"]
        assert payload["base"] == "develop"
        assert payload["body"] == "PR body"

    async def test_create_pr_api_error(self):
        ctx, client = _mock_context()
        client.post = AsyncMock(return_value=_github_response(422, text="Conflict"))
        result = await ToolService._registry["github_create_pr"][0](
            {"repo": "repo", "title": "PR", "head": "dev"},
            ctx,
        )
        assert "error" in result

    async def test_create_pr_no_credentials(self):
        ctx, _ = _mock_context(token="", owner="")
        result = await ToolService._registry["github_create_pr"][0](
            {"repo": "repo", "title": "PR", "head": "dev"},
            ctx,
        )
        assert "not configured" in result["error"]


class TestGitHubComment:
    async def test_comment_success(self):
        ctx, client = _mock_context()
        client.post = AsyncMock(
            return_value=_github_response(
                201,
                {
                    "id": 999,
                    "html_url": "https://github.com/myorg/repo/issues/1#issuecomment-999",
                },
            )
        )
        result = await ToolService._registry["github_comment"][0](
            {"repo": "repo", "issue_number": 1, "body": "LGTM"},
            ctx,
        )
        assert result["comment_id"] == 999

    async def test_comment_api_error(self):
        ctx, client = _mock_context()
        client.post = AsyncMock(return_value=_github_response(404, text="Not Found"))
        result = await ToolService._registry["github_comment"][0](
            {"repo": "repo", "issue_number": 999, "body": "Hello"},
            ctx,
        )
        assert "error" in result
        assert "404" in result["error"]

    async def test_comment_no_credentials(self):
        ctx, _ = _mock_context(token="", owner="myorg")
        result = await ToolService._registry["github_comment"][0](
            {"repo": "repo", "issue_number": 1, "body": "Hi"},
            ctx,
        )
        assert "not configured" in result["error"]


class TestGitHubListRuns:
    async def test_list_runs_success(self):
        ctx, client = _mock_context()
        client.get = AsyncMock(
            return_value=_github_response(
                200,
                {
                    "total_count": 2,
                    "workflow_runs": [
                        {
                            "id": 100,
                            "name": "CI",
                            "status": "completed",
                            "conclusion": "success",
                            "head_branch": "main",
                            "head_sha": "abc12345678",
                            "html_url": "https://github.com/myorg/repo/actions/runs/100",
                            "created_at": "2026-02-12T10:00:00Z",
                        },
                        {
                            "id": 99,
                            "name": "CI",
                            "status": "completed",
                            "conclusion": "failure",
                            "head_branch": "feature",
                            "head_sha": "def45678901",
                            "html_url": "https://github.com/myorg/repo/actions/runs/99",
                            "created_at": "2026-02-12T09:00:00Z",
                        },
                    ],
                },
            )
        )
        result = await ToolService._registry["github_list_runs"][0](
            {"repo": "repo"},
            ctx,
        )
        assert result["total_count"] == 2
        assert len(result["runs"]) == 2
        assert result["runs"][0]["id"] == 100
        assert result["runs"][0]["conclusion"] == "success"
        assert result["runs"][0]["commit_sha"] == "abc12345"

    async def test_list_runs_with_branch_filter(self):
        ctx, client = _mock_context()
        client.get = AsyncMock(
            return_value=_github_response(
                200,
                {
                    "total_count": 0,
                    "workflow_runs": [],
                },
            )
        )
        await ToolService._registry["github_list_runs"][0](
            {"repo": "repo", "branch": "main", "per_page": 3},
            ctx,
        )
        call_params = client.get.call_args[1]["params"]
        assert call_params["branch"] == "main"
        assert call_params["per_page"] == 3

    async def test_list_runs_caps_per_page(self):
        ctx, client = _mock_context()
        client.get = AsyncMock(
            return_value=_github_response(
                200,
                {
                    "total_count": 0,
                    "workflow_runs": [],
                },
            )
        )
        await ToolService._registry["github_list_runs"][0](
            {"repo": "repo", "per_page": 100},
            ctx,
        )
        call_params = client.get.call_args[1]["params"]
        assert call_params["per_page"] == 10

    async def test_list_runs_api_error(self):
        ctx, client = _mock_context()
        client.get = AsyncMock(return_value=_github_response(403, text="Forbidden"))
        result = await ToolService._registry["github_list_runs"][0](
            {"repo": "repo"},
            ctx,
        )
        assert "error" in result
        assert "403" in result["error"]

    async def test_list_runs_no_credentials(self):
        ctx, _ = _mock_context(token="", owner="myorg")
        result = await ToolService._registry["github_list_runs"][0](
            {"repo": "repo"},
            ctx,
        )
        assert "not configured" in result["error"]


class TestGitHubGetRunLogs:
    async def test_get_run_logs_success_with_failed_job(self):
        ctx, client = _mock_context()

        jobs_response = _github_response(
            200,
            {
                "jobs": [
                    {
                        "id": 501,
                        "name": "build",
                        "status": "completed",
                        "conclusion": "failure",
                        "steps": [
                            {"name": "Checkout", "status": "completed", "conclusion": "success"},
                            {"name": "Test", "status": "completed", "conclusion": "failure"},
                        ],
                    },
                ],
            },
        )
        log_response = _github_response(200, text="Error: test_login failed\nAssertionError")
        log_response.text = "Error: test_login failed\nAssertionError"

        client.get = AsyncMock(side_effect=[jobs_response, log_response])
        result = await ToolService._registry["github_get_run_logs"][0](
            {"repo": "repo", "run_id": 100},
            ctx,
        )
        assert len(result["jobs"]) == 1
        assert result["jobs"][0]["conclusion"] == "failure"
        assert "test_login" in result["jobs"][0]["logs"]
        assert len(result["jobs"][0]["steps"]) == 2

    async def test_get_run_logs_success_job(self):
        ctx, client = _mock_context()

        jobs_response = _github_response(
            200,
            {
                "jobs": [
                    {
                        "id": 502,
                        "name": "lint",
                        "status": "completed",
                        "conclusion": "success",
                        "steps": [{"name": "Lint", "status": "completed", "conclusion": "success"}],
                    },
                ],
            },
        )
        log_response = _github_response(200)
        log_response.text = "All checks passed"

        client.get = AsyncMock(side_effect=[jobs_response, log_response])
        result = await ToolService._registry["github_get_run_logs"][0](
            {"repo": "repo", "run_id": 101},
            ctx,
        )
        assert result["jobs"][0]["logs"] == "All checks passed"

    async def test_get_run_logs_in_progress_no_logs(self):
        ctx, client = _mock_context()

        jobs_response = _github_response(
            200,
            {
                "jobs": [
                    {
                        "id": 503,
                        "name": "deploy",
                        "status": "in_progress",
                        "conclusion": None,
                        "steps": [],
                    },
                ],
            },
        )
        client.get = AsyncMock(return_value=jobs_response)
        result = await ToolService._registry["github_get_run_logs"][0](
            {"repo": "repo", "run_id": 102},
            ctx,
        )
        assert "logs" not in result["jobs"][0]

    async def test_get_run_logs_log_fetch_fails(self):
        ctx, client = _mock_context()

        jobs_response = _github_response(
            200,
            {
                "jobs": [
                    {
                        "id": 504,
                        "name": "build",
                        "status": "completed",
                        "conclusion": "failure",
                        "steps": [],
                    },
                ],
            },
        )
        log_error = _github_response(500, text="Internal Server Error")

        client.get = AsyncMock(side_effect=[jobs_response, log_error])
        result = await ToolService._registry["github_get_run_logs"][0](
            {"repo": "repo", "run_id": 103},
            ctx,
        )
        assert "log fetch failed: 500" in result["jobs"][0]["logs"]

    async def test_get_run_logs_jobs_api_error(self):
        ctx, client = _mock_context()
        client.get = AsyncMock(return_value=_github_response(404, text="Not Found"))
        result = await ToolService._registry["github_get_run_logs"][0](
            {"repo": "repo", "run_id": 999},
            ctx,
        )
        assert "error" in result
        assert "404" in result["error"]

    async def test_get_run_logs_no_credentials(self):
        ctx, _ = _mock_context(token="", owner="myorg")
        result = await ToolService._registry["github_get_run_logs"][0](
            {"repo": "repo", "run_id": 100},
            ctx,
        )
        assert "not configured" in result["error"]

    async def test_get_run_logs_cancelled_job(self):
        ctx, client = _mock_context()

        jobs_response = _github_response(
            200,
            {
                "jobs": [
                    {
                        "id": 505,
                        "name": "build",
                        "status": "completed",
                        "conclusion": "cancelled",
                        "steps": [],
                    },
                ],
            },
        )
        log_response = _github_response(200)
        log_response.text = "Cancelled by user"

        client.get = AsyncMock(side_effect=[jobs_response, log_response])
        result = await ToolService._registry["github_get_run_logs"][0](
            {"repo": "repo", "run_id": 104},
            ctx,
        )
        assert result["jobs"][0]["logs"] == "Cancelled by user"


class TestGitHubGetIssue:
    async def test_get_issue_success(self):
        ctx, client = _mock_context()
        client.get = AsyncMock(
            return_value=_github_response(
                200,
                {
                    "number": 42,
                    "title": "Bug report",
                    "body": "Details here",
                    "state": "open",
                    "labels": [{"name": "bug"}],
                    "assignees": [{"login": "alice"}],
                    "comments": 3,
                    "html_url": "https://github.com/myorg/repo/issues/42",
                    "created_at": "2026-02-01T00:00:00Z",
                    "updated_at": "2026-02-10T00:00:00Z",
                },
            )
        )
        result = await ToolService._registry["github_get_issue"][0](
            {"repo": "repo", "issue_number": 42},
            ctx,
        )
        assert result["issue_number"] == 42
        assert result["title"] == "Bug report"
        assert result["body"] == "Details here"
        assert result["state"] == "open"
        assert result["labels"] == ["bug"]
        assert result["assignees"] == ["alice"]
        assert result["comments"] == 3
        assert "url" in result

    async def test_get_issue_empty_body(self):
        ctx, client = _mock_context()
        client.get = AsyncMock(
            return_value=_github_response(
                200,
                {
                    "number": 1,
                    "title": "No body",
                    "body": None,
                    "state": "open",
                    "labels": [],
                    "assignees": [],
                    "comments": 0,
                    "html_url": "https://github.com/myorg/repo/issues/1",
                    "created_at": "2026-02-01T00:00:00Z",
                    "updated_at": "2026-02-01T00:00:00Z",
                },
            )
        )
        result = await ToolService._registry["github_get_issue"][0](
            {"repo": "repo", "issue_number": 1},
            ctx,
        )
        assert result["body"] == ""

    async def test_get_issue_api_error(self):
        ctx, client = _mock_context()
        client.get = AsyncMock(return_value=_github_response(404, text="Not Found"))
        result = await ToolService._registry["github_get_issue"][0](
            {"repo": "repo", "issue_number": 999},
            ctx,
        )
        assert "error" in result
        assert "404" in result["error"]

    async def test_get_issue_no_credentials(self):
        ctx, _ = _mock_context(token="", owner="myorg")
        result = await ToolService._registry["github_get_issue"][0](
            {"repo": "repo", "issue_number": 1},
            ctx,
        )
        assert "not configured" in result["error"]


class TestGitHubGetPr:
    async def test_get_pr_success(self):
        ctx, client = _mock_context()
        client.get = AsyncMock(
            return_value=_github_response(
                200,
                {
                    "number": 10,
                    "title": "Add feature",
                    "body": "PR description",
                    "state": "open",
                    "head": {"ref": "feature-x"},
                    "base": {"ref": "main"},
                    "merged": False,
                    "mergeable": True,
                    "html_url": "https://github.com/myorg/repo/pull/10",
                    "diff_url": "https://github.com/myorg/repo/pull/10.diff",
                    "created_at": "2026-02-05T00:00:00Z",
                    "updated_at": "2026-02-10T00:00:00Z",
                },
            )
        )
        result = await ToolService._registry["github_get_pr"][0](
            {"repo": "repo", "pr_number": 10},
            ctx,
        )
        assert result["pr_number"] == 10
        assert result["title"] == "Add feature"
        assert result["head"] == "feature-x"
        assert result["base"] == "main"
        assert result["merged"] is False
        assert result["mergeable"] is True
        assert "diff_url" in result

    async def test_get_pr_merged(self):
        ctx, client = _mock_context()
        client.get = AsyncMock(
            return_value=_github_response(
                200,
                {
                    "number": 5,
                    "title": "Merged PR",
                    "body": None,
                    "state": "closed",
                    "head": {"ref": "fix"},
                    "base": {"ref": "main"},
                    "merged": True,
                    "mergeable": None,
                    "html_url": "https://github.com/myorg/repo/pull/5",
                    "diff_url": "https://github.com/myorg/repo/pull/5.diff",
                    "created_at": "2026-01-01T00:00:00Z",
                    "updated_at": "2026-01-02T00:00:00Z",
                },
            )
        )
        result = await ToolService._registry["github_get_pr"][0](
            {"repo": "repo", "pr_number": 5},
            ctx,
        )
        assert result["merged"] is True
        assert result["state"] == "closed"
        assert result["body"] == ""

    async def test_get_pr_api_error(self):
        ctx, client = _mock_context()
        client.get = AsyncMock(return_value=_github_response(404, text="Not Found"))
        result = await ToolService._registry["github_get_pr"][0](
            {"repo": "repo", "pr_number": 999},
            ctx,
        )
        assert "error" in result
        assert "404" in result["error"]

    async def test_get_pr_no_credentials(self):
        ctx, _ = _mock_context(token="ghp_test", owner="")
        result = await ToolService._registry["github_get_pr"][0](
            {"repo": "repo", "pr_number": 1},
            ctx,
        )
        assert "not configured" in result["error"]


class TestGitHubListComments:
    async def test_list_comments_success(self):
        ctx, client = _mock_context()
        client.get = AsyncMock(
            return_value=_github_response(
                200,
                [
                    {
                        "id": 100,
                        "user": {"login": "alice"},
                        "body": "Looks good",
                        "created_at": "2026-02-01T00:00:00Z",
                        "updated_at": "2026-02-01T00:00:00Z",
                        "html_url": "https://github.com/myorg/repo/issues/1#issuecomment-100",
                    },
                    {
                        "id": 101,
                        "user": {"login": "bob"},
                        "body": "Needs fix",
                        "created_at": "2026-02-02T00:00:00Z",
                        "updated_at": "2026-02-02T00:00:00Z",
                        "html_url": "https://github.com/myorg/repo/issues/1#issuecomment-101",
                    },
                ],
            )
        )
        result = await ToolService._registry["github_list_comments"][0](
            {"repo": "repo", "issue_number": 1},
            ctx,
        )
        assert len(result["comments"]) == 2
        assert result["comments"][0]["author"] == "alice"
        assert result["comments"][0]["body"] == "Looks good"
        assert result["comments"][1]["author"] == "bob"

    async def test_list_comments_caps_per_page(self):
        ctx, client = _mock_context()
        client.get = AsyncMock(return_value=_github_response(200, []))
        await ToolService._registry["github_list_comments"][0](
            {"repo": "repo", "issue_number": 1, "per_page": 100},
            ctx,
        )
        call_params = client.get.call_args[1]["params"]
        assert call_params["per_page"] == 30

    async def test_list_comments_api_error(self):
        ctx, client = _mock_context()
        client.get = AsyncMock(return_value=_github_response(404, text="Not Found"))
        result = await ToolService._registry["github_list_comments"][0](
            {"repo": "repo", "issue_number": 999},
            ctx,
        )
        assert "error" in result
        assert "404" in result["error"]

    async def test_list_comments_no_credentials(self):
        ctx, _ = _mock_context(token="", owner="")
        result = await ToolService._registry["github_list_comments"][0](
            {"repo": "repo", "issue_number": 1},
            ctx,
        )
        assert "not configured" in result["error"]


class TestGitHubListReviewComments:
    async def test_list_review_comments_success(self):
        ctx, client = _mock_context()
        client.get = AsyncMock(
            return_value=_github_response(
                200,
                [
                    {
                        "id": 200,
                        "user": {"login": "reviewer1"},
                        "body": "Needs refactor",
                        "path": "src/main.py",
                        "line": 42,
                        "side": "RIGHT",
                        "diff_hunk": "@@ -40,3 +40,5 @@\n+new code",
                        "created_at": "2026-02-03T00:00:00Z",
                        "html_url": "https://github.com/myorg/repo/pull/10#discussion_r200",
                    },
                    {
                        "id": 201,
                        "user": {"login": "reviewer2"},
                        "body": "LGTM",
                        "path": "src/utils.py",
                        "line": None,
                        "side": None,
                        "diff_hunk": "@@ -1,2 +1,3 @@",
                        "created_at": "2026-02-04T00:00:00Z",
                        "html_url": "https://github.com/myorg/repo/pull/10#discussion_r201",
                    },
                ],
            )
        )
        result = await ToolService._registry["github_list_review_comments"][0](
            {"repo": "repo", "pr_number": 10},
            ctx,
        )
        assert len(result["review_comments"]) == 2
        assert result["review_comments"][0]["author"] == "reviewer1"
        assert result["review_comments"][0]["path"] == "src/main.py"
        assert result["review_comments"][0]["line"] == 42
        assert result["review_comments"][1]["line"] is None

    async def test_list_review_comments_caps_per_page(self):
        ctx, client = _mock_context()
        client.get = AsyncMock(return_value=_github_response(200, []))
        await ToolService._registry["github_list_review_comments"][0](
            {"repo": "repo", "pr_number": 1, "per_page": 100},
            ctx,
        )
        call_params = client.get.call_args[1]["params"]
        assert call_params["per_page"] == 30

    async def test_list_review_comments_api_error(self):
        ctx, client = _mock_context()
        client.get = AsyncMock(return_value=_github_response(404, text="Not Found"))
        result = await ToolService._registry["github_list_review_comments"][0](
            {"repo": "repo", "pr_number": 999},
            ctx,
        )
        assert "error" in result
        assert "404" in result["error"]

    async def test_list_review_comments_no_credentials(self):
        ctx, _ = _mock_context(token="", owner="myorg")
        result = await ToolService._registry["github_list_review_comments"][0](
            {"repo": "repo", "pr_number": 1},
            ctx,
        )
        assert "not configured" in result["error"]


class TestGitHubUpdateIssue:
    async def test_update_issue_success(self):
        ctx, client = _mock_context()
        client.patch = AsyncMock(
            return_value=_github_response(
                200,
                {
                    "number": 42,
                    "state": "closed",
                    "html_url": "https://github.com/myorg/repo/issues/42",
                },
            )
        )
        result = await ToolService._registry["github_update_issue"][0](
            {"repo": "repo", "issue_number": 42, "state": "closed"},
            ctx,
        )
        assert result["issue_number"] == 42
        assert result["state"] == "closed"

    async def test_update_issue_title_and_body(self):
        ctx, client = _mock_context()
        client.patch = AsyncMock(
            return_value=_github_response(
                200,
                {
                    "number": 1,
                    "state": "open",
                    "html_url": "https://github.com/myorg/repo/issues/1",
                },
            )
        )
        result = await ToolService._registry["github_update_issue"][0](
            {"repo": "repo", "issue_number": 1, "title": "New Title", "body": "Updated body"},
            ctx,
        )
        assert result["issue_number"] == 1
        payload = client.patch.call_args[1]["json"]
        assert payload["title"] == "New Title"
        assert payload["body"] == "Updated body"

    async def test_update_issue_labels(self):
        ctx, client = _mock_context()
        client.patch = AsyncMock(
            return_value=_github_response(
                200,
                {
                    "number": 5,
                    "state": "open",
                    "html_url": "https://github.com/myorg/repo/issues/5",
                },
            )
        )
        result = await ToolService._registry["github_update_issue"][0](
            {"repo": "repo", "issue_number": 5, "labels": ["bug", "urgent"]},
            ctx,
        )
        assert result["issue_number"] == 5
        payload = client.patch.call_args[1]["json"]
        assert payload["labels"] == ["bug", "urgent"]

    async def test_update_issue_no_fields(self):
        ctx, _ = _mock_context()
        result = await ToolService._registry["github_update_issue"][0](
            {"repo": "repo", "issue_number": 1},
            ctx,
        )
        assert result["error"] == "No fields to update"

    async def test_update_issue_api_error(self):
        ctx, client = _mock_context()
        client.patch = AsyncMock(return_value=_github_response(404, text="Not Found"))
        result = await ToolService._registry["github_update_issue"][0](
            {"repo": "repo", "issue_number": 999, "state": "closed"},
            ctx,
        )
        assert "error" in result
        assert "404" in result["error"]

    async def test_update_issue_no_credentials(self):
        ctx, _ = _mock_context(token="", owner="myorg")
        result = await ToolService._registry["github_update_issue"][0](
            {"repo": "repo", "issue_number": 1, "state": "closed"},
            ctx,
        )
        assert "not configured" in result["error"]


class TestGitHubUpdatePr:
    async def test_update_pr_success(self):
        ctx, client = _mock_context()
        client.patch = AsyncMock(
            return_value=_github_response(
                200,
                {
                    "number": 10,
                    "state": "closed",
                    "html_url": "https://github.com/myorg/repo/pull/10",
                },
            )
        )
        result = await ToolService._registry["github_update_pr"][0](
            {"repo": "repo", "pr_number": 10, "state": "closed"},
            ctx,
        )
        assert result["pr_number"] == 10
        assert result["state"] == "closed"

    async def test_update_pr_title_body_base(self):
        ctx, client = _mock_context()
        client.patch = AsyncMock(
            return_value=_github_response(
                200,
                {
                    "number": 11,
                    "state": "open",
                    "html_url": "https://github.com/myorg/repo/pull/11",
                },
            )
        )
        result = await ToolService._registry["github_update_pr"][0](
            {
                "repo": "repo",
                "pr_number": 11,
                "title": "Updated PR",
                "body": "New desc",
                "base": "develop",
            },
            ctx,
        )
        assert result["pr_number"] == 11
        payload = client.patch.call_args[1]["json"]
        assert payload["title"] == "Updated PR"
        assert payload["body"] == "New desc"
        assert payload["base"] == "develop"

    async def test_update_pr_no_fields(self):
        ctx, _ = _mock_context()
        result = await ToolService._registry["github_update_pr"][0](
            {"repo": "repo", "pr_number": 1},
            ctx,
        )
        assert result["error"] == "No fields to update"

    async def test_update_pr_api_error(self):
        ctx, client = _mock_context()
        client.patch = AsyncMock(return_value=_github_response(422, text="Validation Failed"))
        result = await ToolService._registry["github_update_pr"][0](
            {"repo": "repo", "pr_number": 10, "title": "X"},
            ctx,
        )
        assert "error" in result
        assert "422" in result["error"]

    async def test_update_pr_no_credentials(self):
        ctx, _ = _mock_context(token="", owner="")
        result = await ToolService._registry["github_update_pr"][0](
            {"repo": "repo", "pr_number": 1, "state": "closed"},
            ctx,
        )
        assert "not configured" in result["error"]


class TestGitHubUpdateComment:
    async def test_update_comment_success(self):
        ctx, client = _mock_context()
        client.patch = AsyncMock(
            return_value=_github_response(
                200,
                {
                    "id": 999,
                    "html_url": "https://github.com/myorg/repo/issues/1#issuecomment-999",
                },
            )
        )
        result = await ToolService._registry["github_update_comment"][0](
            {"repo": "repo", "comment_id": 999, "body": "Updated comment"},
            ctx,
        )
        assert result["comment_id"] == 999
        assert "url" in result

    async def test_update_comment_api_error(self):
        ctx, client = _mock_context()
        client.patch = AsyncMock(return_value=_github_response(404, text="Not Found"))
        result = await ToolService._registry["github_update_comment"][0](
            {"repo": "repo", "comment_id": 999, "body": "X"},
            ctx,
        )
        assert "error" in result
        assert "404" in result["error"]

    async def test_update_comment_no_credentials(self):
        ctx, _ = _mock_context(token="ghp_test", owner="")
        result = await ToolService._registry["github_update_comment"][0](
            {"repo": "repo", "comment_id": 1, "body": "X"},
            ctx,
        )
        assert "not configured" in result["error"]


class TestGitHubDeleteComment:
    async def test_delete_comment_success(self):
        ctx, client = _mock_context()
        client.delete = AsyncMock(return_value=_github_response(204))
        result = await ToolService._registry["github_delete_comment"][0](
            {"repo": "repo", "comment_id": 999},
            ctx,
        )
        assert result["deleted"] is True

    async def test_delete_comment_api_error(self):
        ctx, client = _mock_context()
        client.delete = AsyncMock(return_value=_github_response(404, text="Not Found"))
        result = await ToolService._registry["github_delete_comment"][0](
            {"repo": "repo", "comment_id": 999},
            ctx,
        )
        assert "error" in result
        assert "404" in result["error"]

    async def test_delete_comment_no_credentials(self):
        ctx, _ = _mock_context(token="", owner="myorg")
        result = await ToolService._registry["github_delete_comment"][0](
            {"repo": "repo", "comment_id": 1},
            ctx,
        )
        assert "not configured" in result["error"]
