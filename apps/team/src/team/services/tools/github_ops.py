# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""GitHub tools — CRUD for issues, PRs, comments, and CI/CD logs via GitHub REST API."""

from team.config import get_settings
from team.services.tool_service import ToolService

GITHUB_API = "https://api.github.com"
MAX_LOG_LENGTH = 8000


def _get_github_token(context: dict) -> str:
    """Resolve GitHub token: agent credentials first, then global settings."""
    agent_config = context.get("agent_config", {})
    token = agent_config.get("credentials", {}).get("github_token", "")
    if token:
        return token
    return get_settings().github_token


def _get_github_owner(context: dict) -> str:
    """Resolve GitHub owner: agent credentials first, then global settings."""
    agent_config = context.get("agent_config", {})
    owner = agent_config.get("credentials", {}).get("github_owner", "")
    if owner:
        return owner
    return get_settings().github_owner


def _normalize_repo(repo: str, default_owner: str) -> tuple[str, str]:
    """Handle both 'repo' and 'owner/repo' formats.

    Returns (owner, repo_name).  If *repo* contains a slash the owner
    portion overrides *default_owner* so agents can target repos outside
    the default organisation.
    """
    if "/" in repo:
        parts = repo.split("/", 1)
        return parts[0], parts[1]
    return default_owner, repo


# --- github_create_issue ---

ISSUE_DEFINITION = {
    "name": "github_create_issue",
    "description": "Create a GitHub issue in a repository.",
    "parameters": {
        "type": "object",
        "properties": {
            "repo": {
                "type": "string",
                "description": "Repository name, e.g. 'myrepo' or 'owner/myrepo'",
            },
            "title": {"type": "string", "description": "Issue title"},
            "body": {"type": "string", "description": "Issue body (markdown)"},
            "labels": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Labels to apply",
            },
        },
        "required": ["repo", "title"],
    },
}


@ToolService.register("github_create_issue", ISSUE_DEFINITION)
async def github_create_issue(params: dict, context: dict) -> dict:
    """Create a GitHub issue."""
    token = _get_github_token(context)
    owner = _get_github_owner(context)
    if not token or not owner:
        return {"error": "GitHub token or owner not configured"}
    owner, repo = _normalize_repo(params["repo"], owner)

    tool_service: ToolService = context["tool_service"]
    client = await tool_service.get_client()

    payload: dict = {"title": params["title"]}
    if params.get("body"):
        payload["body"] = params["body"]
    if params.get("labels"):
        payload["labels"] = params["labels"]

    response = await client.post(
        f"{GITHUB_API}/repos/{owner}/{repo}/issues",
        headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"},
        json=payload,
    )
    if response.status_code == 201:
        data = response.json()
        return {"issue_number": data["number"], "url": data["html_url"]}
    return {"error": f"GitHub API error {response.status_code}: {response.text[:500]}"}


# --- github_create_pr ---

PR_DEFINITION = {
    "name": "github_create_pr",
    "description": "Create a GitHub pull request.",
    "parameters": {
        "type": "object",
        "properties": {
            "repo": {
                "type": "string",
                "description": "Repository name, e.g. 'myrepo' or 'owner/myrepo'",
            },
            "title": {"type": "string", "description": "PR title"},
            "head": {"type": "string", "description": "Source branch"},
            "base": {"type": "string", "description": "Target branch", "default": "main"},
            "body": {"type": "string", "description": "PR description (markdown)"},
        },
        "required": ["repo", "title", "head"],
    },
}


@ToolService.register("github_create_pr", PR_DEFINITION)
async def github_create_pr(params: dict, context: dict) -> dict:
    """Create a GitHub pull request."""
    token = _get_github_token(context)
    owner = _get_github_owner(context)
    if not token or not owner:
        return {"error": "GitHub token or owner not configured"}
    owner, repo = _normalize_repo(params["repo"], owner)

    tool_service: ToolService = context["tool_service"]
    client = await tool_service.get_client()

    payload: dict = {
        "title": params["title"],
        "head": params["head"],
        "base": params.get("base", "main"),
    }
    if params.get("body"):
        payload["body"] = params["body"]

    response = await client.post(
        f"{GITHUB_API}/repos/{owner}/{repo}/pulls",
        headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"},
        json=payload,
    )
    if response.status_code == 201:
        data = response.json()
        return {"pr_number": data["number"], "url": data["html_url"]}
    return {"error": f"GitHub API error {response.status_code}: {response.text[:500]}"}


# --- github_comment ---

COMMENT_DEFINITION = {
    "name": "github_comment",
    "description": "Add a comment to a GitHub issue or pull request.",
    "parameters": {
        "type": "object",
        "properties": {
            "repo": {
                "type": "string",
                "description": "Repository name, e.g. 'myrepo' or 'owner/myrepo'",
            },
            "issue_number": {"type": "integer", "description": "Issue or PR number"},
            "body": {"type": "string", "description": "Comment body (markdown)"},
        },
        "required": ["repo", "issue_number", "body"],
    },
}


@ToolService.register("github_comment", COMMENT_DEFINITION)
async def github_comment(params: dict, context: dict) -> dict:
    """Add a comment to a GitHub issue or PR."""
    token = _get_github_token(context)
    owner = _get_github_owner(context)
    if not token or not owner:
        return {"error": "GitHub token or owner not configured"}
    owner, repo = _normalize_repo(params["repo"], owner)

    tool_service: ToolService = context["tool_service"]
    client = await tool_service.get_client()

    response = await client.post(
        f"{GITHUB_API}/repos/{owner}/{repo}/issues/{params['issue_number']}/comments",
        headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"},
        json={"body": params["body"]},
    )
    if response.status_code == 201:
        data = response.json()
        return {"comment_id": data["id"], "url": data["html_url"]}
    return {"error": f"GitHub API error {response.status_code}: {response.text[:500]}"}


# --- github_get_issue ---

GET_ISSUE_DEFINITION = {
    "name": "github_get_issue",
    "description": "Read a GitHub issue — returns title, body, state, labels, assignees, and comment count.",
    "parameters": {
        "type": "object",
        "properties": {
            "repo": {
                "type": "string",
                "description": "Repository name, e.g. 'myrepo' or 'owner/myrepo'",
            },
            "issue_number": {"type": "integer", "description": "Issue number"},
        },
        "required": ["repo", "issue_number"],
    },
}


@ToolService.register("github_get_issue", GET_ISSUE_DEFINITION)
async def github_get_issue(params: dict, context: dict) -> dict:
    """Read a GitHub issue."""
    token = _get_github_token(context)
    owner = _get_github_owner(context)
    if not token or not owner:
        return {"error": "GitHub token or owner not configured"}
    owner, repo = _normalize_repo(params["repo"], owner)

    tool_service: ToolService = context["tool_service"]
    client = await tool_service.get_client()

    response = await client.get(
        f"{GITHUB_API}/repos/{owner}/{repo}/issues/{params['issue_number']}",
        headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"},
    )
    if response.status_code == 200:
        data = response.json()
        return {
            "issue_number": data["number"],
            "title": data["title"],
            "body": data.get("body") or "",
            "state": data["state"],
            "labels": [label["name"] for label in data.get("labels", [])],
            "assignees": [a["login"] for a in data.get("assignees", [])],
            "comments": data.get("comments", 0),
            "url": data["html_url"],
            "created_at": data["created_at"],
            "updated_at": data["updated_at"],
        }
    return {"error": f"GitHub API error {response.status_code}: {response.text[:500]}"}


# --- github_get_pr ---

GET_PR_DEFINITION = {
    "name": "github_get_pr",
    "description": "Read a GitHub pull request — returns title, body, state, branches, merge status, and diff URL.",
    "parameters": {
        "type": "object",
        "properties": {
            "repo": {
                "type": "string",
                "description": "Repository name, e.g. 'myrepo' or 'owner/myrepo'",
            },
            "pr_number": {"type": "integer", "description": "Pull request number"},
        },
        "required": ["repo", "pr_number"],
    },
}


@ToolService.register("github_get_pr", GET_PR_DEFINITION)
async def github_get_pr(params: dict, context: dict) -> dict:
    """Read a GitHub pull request."""
    token = _get_github_token(context)
    owner = _get_github_owner(context)
    if not token or not owner:
        return {"error": "GitHub token or owner not configured"}
    owner, repo = _normalize_repo(params["repo"], owner)

    tool_service: ToolService = context["tool_service"]
    client = await tool_service.get_client()

    response = await client.get(
        f"{GITHUB_API}/repos/{owner}/{repo}/pulls/{params['pr_number']}",
        headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"},
    )
    if response.status_code == 200:
        data = response.json()
        return {
            "pr_number": data["number"],
            "title": data["title"],
            "body": data.get("body") or "",
            "state": data["state"],
            "head": data["head"]["ref"],
            "base": data["base"]["ref"],
            "merged": data.get("merged", False),
            "mergeable": data.get("mergeable"),
            "url": data["html_url"],
            "diff_url": data["diff_url"],
            "created_at": data["created_at"],
            "updated_at": data["updated_at"],
        }
    return {"error": f"GitHub API error {response.status_code}: {response.text[:500]}"}


# --- github_update_issue ---

UPDATE_ISSUE_DEFINITION = {
    "name": "github_update_issue",
    "description": "Update a GitHub issue (title, body, state, labels). Set state to 'closed' to close it.",
    "parameters": {
        "type": "object",
        "properties": {
            "repo": {
                "type": "string",
                "description": "Repository name, e.g. 'myrepo' or 'owner/myrepo'",
            },
            "issue_number": {"type": "integer", "description": "Issue number"},
            "title": {"type": "string", "description": "New title"},
            "body": {"type": "string", "description": "New body (markdown)"},
            "state": {
                "type": "string",
                "enum": ["open", "closed"],
                "description": "Set to 'closed' to close the issue",
            },
            "labels": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Replace labels",
            },
        },
        "required": ["repo", "issue_number"],
    },
}


@ToolService.register("github_update_issue", UPDATE_ISSUE_DEFINITION)
async def github_update_issue(params: dict, context: dict) -> dict:
    """Update a GitHub issue."""
    token = _get_github_token(context)
    owner = _get_github_owner(context)
    if not token or not owner:
        return {"error": "GitHub token or owner not configured"}
    owner, repo = _normalize_repo(params["repo"], owner)

    tool_service: ToolService = context["tool_service"]
    client = await tool_service.get_client()

    payload: dict = {}
    for key in ("title", "body", "state", "labels"):
        if key in params:
            payload[key] = params[key]
    if not payload:
        return {"error": "No fields to update"}

    response = await client.patch(
        f"{GITHUB_API}/repos/{owner}/{repo}/issues/{params['issue_number']}",
        headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"},
        json=payload,
    )
    if response.status_code == 200:
        data = response.json()
        return {"issue_number": data["number"], "state": data["state"], "url": data["html_url"]}
    return {"error": f"GitHub API error {response.status_code}: {response.text[:500]}"}


# --- github_update_pr ---

UPDATE_PR_DEFINITION = {
    "name": "github_update_pr",
    "description": "Update a GitHub pull request (title, body, state, base). Set state to 'closed' to close it.",
    "parameters": {
        "type": "object",
        "properties": {
            "repo": {
                "type": "string",
                "description": "Repository name, e.g. 'myrepo' or 'owner/myrepo'",
            },
            "pr_number": {"type": "integer", "description": "Pull request number"},
            "title": {"type": "string", "description": "New title"},
            "body": {"type": "string", "description": "New body (markdown)"},
            "state": {
                "type": "string",
                "enum": ["open", "closed"],
                "description": "Set to 'closed' to close the PR",
            },
            "base": {"type": "string", "description": "Change target branch"},
        },
        "required": ["repo", "pr_number"],
    },
}


@ToolService.register("github_update_pr", UPDATE_PR_DEFINITION)
async def github_update_pr(params: dict, context: dict) -> dict:
    """Update a GitHub pull request."""
    token = _get_github_token(context)
    owner = _get_github_owner(context)
    if not token or not owner:
        return {"error": "GitHub token or owner not configured"}
    owner, repo = _normalize_repo(params["repo"], owner)

    tool_service: ToolService = context["tool_service"]
    client = await tool_service.get_client()

    payload: dict = {}
    for key in ("title", "body", "state", "base"):
        if key in params:
            payload[key] = params[key]
    if not payload:
        return {"error": "No fields to update"}

    response = await client.patch(
        f"{GITHUB_API}/repos/{owner}/{repo}/pulls/{params['pr_number']}",
        headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"},
        json=payload,
    )
    if response.status_code == 200:
        data = response.json()
        return {"pr_number": data["number"], "state": data["state"], "url": data["html_url"]}
    return {"error": f"GitHub API error {response.status_code}: {response.text[:500]}"}


# --- github_list_comments ---

LIST_COMMENTS_DEFINITION = {
    "name": "github_list_comments",
    "description": "List comments on a GitHub issue or pull request.",
    "parameters": {
        "type": "object",
        "properties": {
            "repo": {
                "type": "string",
                "description": "Repository name, e.g. 'myrepo' or 'owner/myrepo'",
            },
            "issue_number": {"type": "integer", "description": "Issue or PR number"},
            "per_page": {
                "type": "integer",
                "description": "Number of comments to return (max 30)",
                "default": 10,
            },
        },
        "required": ["repo", "issue_number"],
    },
}


@ToolService.register("github_list_comments", LIST_COMMENTS_DEFINITION)
async def github_list_comments(params: dict, context: dict) -> dict:
    """List comments on a GitHub issue or PR."""
    token = _get_github_token(context)
    owner = _get_github_owner(context)
    if not token or not owner:
        return {"error": "GitHub token or owner not configured"}
    owner, repo = _normalize_repo(params["repo"], owner)

    tool_service: ToolService = context["tool_service"]
    client = await tool_service.get_client()

    response = await client.get(
        f"{GITHUB_API}/repos/{owner}/{repo}/issues/{params['issue_number']}/comments",
        headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"},
        params={"per_page": min(params.get("per_page", 10), 30)},
    )
    if response.status_code == 200:
        data = response.json()
        return {
            "comments": [
                {
                    "id": c["id"],
                    "author": c["user"]["login"],
                    "body": c["body"],
                    "created_at": c["created_at"],
                    "updated_at": c["updated_at"],
                    "url": c["html_url"],
                }
                for c in data
            ],
        }
    return {"error": f"GitHub API error {response.status_code}: {response.text[:500]}"}


# --- github_list_review_comments ---

LIST_REVIEW_COMMENTS_DEFINITION = {
    "name": "github_list_review_comments",
    "description": "List inline review comments on a pull request (code-level comments on specific lines/files).",
    "parameters": {
        "type": "object",
        "properties": {
            "repo": {
                "type": "string",
                "description": "Repository name, e.g. 'myrepo' or 'owner/myrepo'",
            },
            "pr_number": {"type": "integer", "description": "Pull request number"},
            "per_page": {
                "type": "integer",
                "description": "Number of review comments to return (max 30)",
                "default": 10,
            },
        },
        "required": ["repo", "pr_number"],
    },
}


@ToolService.register("github_list_review_comments", LIST_REVIEW_COMMENTS_DEFINITION)
async def github_list_review_comments(params: dict, context: dict) -> dict:
    """List inline review comments on a PR."""
    token = _get_github_token(context)
    owner = _get_github_owner(context)
    if not token or not owner:
        return {"error": "GitHub token or owner not configured"}
    owner, repo = _normalize_repo(params["repo"], owner)

    tool_service: ToolService = context["tool_service"]
    client = await tool_service.get_client()

    response = await client.get(
        f"{GITHUB_API}/repos/{owner}/{repo}/pulls/{params['pr_number']}/comments",
        headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"},
        params={"per_page": min(params.get("per_page", 10), 30)},
    )
    if response.status_code == 200:
        data = response.json()
        return {
            "review_comments": [
                {
                    "id": c["id"],
                    "author": c["user"]["login"],
                    "body": c["body"],
                    "path": c["path"],
                    "line": c.get("line"),
                    "side": c.get("side"),
                    "diff_hunk": c.get("diff_hunk", ""),
                    "created_at": c["created_at"],
                    "url": c["html_url"],
                }
                for c in data
            ],
        }
    return {"error": f"GitHub API error {response.status_code}: {response.text[:500]}"}


# --- github_update_comment ---

UPDATE_COMMENT_DEFINITION = {
    "name": "github_update_comment",
    "description": "Edit an existing comment on a GitHub issue or pull request.",
    "parameters": {
        "type": "object",
        "properties": {
            "repo": {
                "type": "string",
                "description": "Repository name, e.g. 'myrepo' or 'owner/myrepo'",
            },
            "comment_id": {"type": "integer", "description": "Comment ID (from github_comment)"},
            "body": {"type": "string", "description": "New comment body (markdown)"},
        },
        "required": ["repo", "comment_id", "body"],
    },
}


@ToolService.register("github_update_comment", UPDATE_COMMENT_DEFINITION)
async def github_update_comment(params: dict, context: dict) -> dict:
    """Edit an existing comment."""
    token = _get_github_token(context)
    owner = _get_github_owner(context)
    if not token or not owner:
        return {"error": "GitHub token or owner not configured"}
    owner, repo = _normalize_repo(params["repo"], owner)

    tool_service: ToolService = context["tool_service"]
    client = await tool_service.get_client()

    response = await client.patch(
        f"{GITHUB_API}/repos/{owner}/{repo}/issues/comments/{params['comment_id']}",
        headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"},
        json={"body": params["body"]},
    )
    if response.status_code == 200:
        data = response.json()
        return {"comment_id": data["id"], "url": data["html_url"]}
    return {"error": f"GitHub API error {response.status_code}: {response.text[:500]}"}


# --- github_delete_comment ---

DELETE_COMMENT_DEFINITION = {
    "name": "github_delete_comment",
    "description": "Delete a comment from a GitHub issue or pull request.",
    "parameters": {
        "type": "object",
        "properties": {
            "repo": {
                "type": "string",
                "description": "Repository name, e.g. 'myrepo' or 'owner/myrepo'",
            },
            "comment_id": {"type": "integer", "description": "Comment ID to delete"},
        },
        "required": ["repo", "comment_id"],
    },
}


@ToolService.register("github_delete_comment", DELETE_COMMENT_DEFINITION)
async def github_delete_comment(params: dict, context: dict) -> dict:
    """Delete a comment."""
    token = _get_github_token(context)
    owner = _get_github_owner(context)
    if not token or not owner:
        return {"error": "GitHub token or owner not configured"}
    owner, repo = _normalize_repo(params["repo"], owner)

    tool_service: ToolService = context["tool_service"]
    client = await tool_service.get_client()

    response = await client.delete(
        f"{GITHUB_API}/repos/{owner}/{repo}/issues/comments/{params['comment_id']}",
        headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"},
    )
    if response.status_code == 204:
        return {"deleted": True}
    return {"error": f"GitHub API error {response.status_code}: {response.text[:500]}"}


# --- github_list_runs ---

LIST_RUNS_DEFINITION = {
    "name": "github_list_runs",
    "description": "List recent GitHub Actions workflow runs for a repository (filter by branch or PR).",
    "parameters": {
        "type": "object",
        "properties": {
            "repo": {
                "type": "string",
                "description": "Repository name, e.g. 'myrepo' or 'owner/myrepo'",
            },
            "branch": {"type": "string", "description": "Filter by branch name"},
            "per_page": {
                "type": "integer",
                "description": "Number of results (max 10)",
                "default": 5,
            },
        },
        "required": ["repo"],
    },
}


@ToolService.register("github_list_runs", LIST_RUNS_DEFINITION)
async def github_list_runs(params: dict, context: dict) -> dict:
    """List recent GitHub Actions workflow runs."""
    token = _get_github_token(context)
    owner = _get_github_owner(context)
    if not token or not owner:
        return {"error": "GitHub token or owner not configured"}
    owner, repo = _normalize_repo(params["repo"], owner)

    tool_service: ToolService = context["tool_service"]
    client = await tool_service.get_client()

    query: dict = {"per_page": min(params.get("per_page", 5), 10)}
    if params.get("branch"):
        query["branch"] = params["branch"]

    response = await client.get(
        f"{GITHUB_API}/repos/{owner}/{repo}/actions/runs",
        headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"},
        params=query,
    )
    if response.status_code != 200:
        return {"error": f"GitHub API error {response.status_code}: {response.text[:500]}"}

    data = response.json()
    runs = [
        {
            "id": r["id"],
            "name": r.get("name", ""),
            "status": r["status"],
            "conclusion": r.get("conclusion"),
            "branch": r["head_branch"],
            "commit_sha": r["head_sha"][:8],
            "url": r["html_url"],
            "created_at": r["created_at"],
        }
        for r in data.get("workflow_runs", [])
    ]
    return {"runs": runs, "total_count": data.get("total_count", 0)}


# --- github_get_run_logs ---

GET_RUN_LOGS_DEFINITION = {
    "name": "github_get_run_logs",
    "description": "Get jobs and logs for a GitHub Actions workflow run (useful to check CI failures).",
    "parameters": {
        "type": "object",
        "properties": {
            "repo": {
                "type": "string",
                "description": "Repository name, e.g. 'myrepo' or 'owner/myrepo'",
            },
            "run_id": {"type": "integer", "description": "Workflow run ID (from github_list_runs)"},
        },
        "required": ["repo", "run_id"],
    },
}


@ToolService.register("github_get_run_logs", GET_RUN_LOGS_DEFINITION)
async def github_get_run_logs(params: dict, context: dict) -> dict:
    """Get jobs and their logs for a workflow run."""
    token = _get_github_token(context)
    owner = _get_github_owner(context)
    if not token or not owner:
        return {"error": "GitHub token or owner not configured"}
    owner, repo = _normalize_repo(params["repo"], owner)

    tool_service: ToolService = context["tool_service"]
    client = await tool_service.get_client()
    headers = {"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"}

    # 1. List jobs for this run
    jobs_response = await client.get(
        f"{GITHUB_API}/repos/{owner}/{repo}/actions/runs/{params['run_id']}/jobs",
        headers=headers,
    )
    if jobs_response.status_code != 200:
        return {
            "error": f"GitHub API error {jobs_response.status_code}: {jobs_response.text[:500]}"
        }

    jobs_data = jobs_response.json()
    results = []

    for job in jobs_data.get("jobs", []):
        job_info: dict = {
            "id": job["id"],
            "name": job["name"],
            "status": job["status"],
            "conclusion": job.get("conclusion"),
            "steps": [
                {
                    "name": s["name"],
                    "status": s["status"],
                    "conclusion": s.get("conclusion"),
                }
                for s in job.get("steps", [])
            ],
        }

        # 2. Fetch logs for failed or completed jobs
        if job.get("conclusion") in ("failure", "cancelled", "success"):
            log_response = await client.get(
                f"{GITHUB_API}/repos/{owner}/{repo}/actions/jobs/{job['id']}/logs",
                headers=headers,
                follow_redirects=True,
            )
            if log_response.status_code == 200:
                job_info["logs"] = log_response.text[:MAX_LOG_LENGTH]
            else:
                job_info["logs"] = f"(log fetch failed: {log_response.status_code})"

        results.append(job_info)

    return {"jobs": results}
