# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Git tools — clone repos and commit/push code using GitPython."""

import asyncio
import logging
import os
from pathlib import Path

from team.config import get_settings
from team.services.tool_service import ToolService

logger = logging.getLogger(__name__)

# Suppress GitPython's hard ImportError when git binary is missing.
# Must be set before the first `import git` anywhere in the process.
os.environ.setdefault("GIT_PYTHON_REFRESH", "quiet")


def _require_git():
    """Import and return the git module, raising a clear error if unavailable."""
    try:
        import git
    except ImportError as exc:
        raise RuntimeError(
            "git is not available — install git on this server or add it to $PATH"
        ) from exc
    if getattr(git, "GIT_OK", None) is False:
        raise RuntimeError("git executable not found in $PATH — install git on this server")
    return git


def _get_git_token(context: dict) -> str:
    """Resolve GitHub token: agent credentials first, then global settings."""
    agent_config = context.get("agent_config", {})
    token = agent_config.get("credentials", {}).get("github_token", "")
    if token:
        return token
    return get_settings().github_token


def _get_git_owner(context: dict) -> str:
    """Resolve GitHub owner: agent credentials first, then global settings."""
    agent_config = context.get("agent_config", {})
    owner = agent_config.get("credentials", {}).get("github_owner", "")
    if owner:
        return owner
    return get_settings().github_owner


def _safe_workspace_path(relative: str, context: dict | None = None) -> Path:
    """Resolve a directory path within the workspace. Raises ValueError on traversal."""
    if context and "workspace_dir" in context:
        workspace = Path(context["workspace_dir"]).resolve()
    else:
        workspace = Path(get_settings().workspace_dir).resolve()
    full = (workspace / relative).resolve()
    if not str(full).startswith(str(workspace)):
        raise ValueError(f"Path traversal blocked: {relative}")
    return full


def _redact_token(text: str, token: str) -> str:
    """Remove token from error messages."""
    if token:
        return text.replace(token, "***")
    return text


def _clone_sync(clone_url: str, target: Path, branch: str | None) -> None:
    """Synchronous clone using GitPython."""
    git = _require_git()
    kwargs: dict = {"to_path": str(target)}
    if branch:
        kwargs["branch"] = branch
    git.Repo.clone_from(clone_url, **kwargs)


def _commit_push_sync(
    repo_path: Path,
    message: str,
    branch: str | None,
) -> None:
    """Synchronous add-all, commit, push using GitPython."""
    git = _require_git()
    repo = git.Repo(str(repo_path))
    repo.git.add("-A")
    repo.index.commit(message)
    if branch:
        repo.remote("origin").push(branch)
    else:
        repo.remote("origin").push()


def _create_branch_sync(repo_path: Path, branch: str, base: str | None) -> str:
    """Create and checkout a new branch. Returns the active branch name."""
    git = _require_git()
    repo = git.Repo(str(repo_path))
    if base:
        repo.git.checkout(base)
    repo.git.checkout("-b", branch)
    return str(repo.active_branch)


def _diff_sync(repo_path: Path) -> str:
    """Return git diff (staged + unstaged) as a string."""
    git = _require_git()
    repo = git.Repo(str(repo_path))
    staged = repo.git.diff("--cached")
    diff = repo.git.diff()
    parts = []
    if staged:
        parts.append(f"=== Staged ===\n{staged}")
    if diff:
        parts.append(f"=== Unstaged ===\n{diff}")
    return "\n\n".join(parts) if parts else "(no changes)"


# --- git_clone ---

CLONE_DEFINITION = {
    "name": "git_clone",
    "description": "Clone a GitHub repository into the workspace.",
    "parameters": {
        "type": "object",
        "properties": {
            "repo": {"type": "string", "description": "Repository name (without owner)"},
            "branch": {"type": "string", "description": "Branch to checkout"},
            "directory": {
                "type": "string",
                "description": "Target directory name within workspace",
            },
        },
        "required": ["repo"],
    },
}


@ToolService.register("git_clone", CLONE_DEFINITION)
async def git_clone(params: dict, context: dict) -> dict:
    """Clone a repository into the workspace."""
    token = _get_git_token(context)
    owner = _get_git_owner(context)
    if not token or not owner:
        return {"error": "GitHub token or owner not configured"}

    repo = params["repo"]
    directory = params.get("directory", repo)

    try:
        target = _safe_workspace_path(directory, context)
    except ValueError as e:
        return {"error": str(e)}

    target.parent.mkdir(parents=True, exist_ok=True)

    clone_url = f"https://x-access-token:{token}@github.com/{owner}/{repo}.git"
    try:
        await asyncio.to_thread(_clone_sync, clone_url, target, params.get("branch"))
    except Exception as e:
        return {"error": _redact_token(str(e), token)}
    return {"cloned": True, "directory": directory}


# --- git_commit_push ---

COMMIT_PUSH_DEFINITION = {
    "name": "git_commit_push",
    "description": "Stage all changes, commit, and push to remote.",
    "parameters": {
        "type": "object",
        "properties": {
            "directory": {"type": "string", "description": "Directory name within workspace"},
            "message": {"type": "string", "description": "Commit message"},
            "branch": {"type": "string", "description": "Branch to push to"},
        },
        "required": ["directory", "message"],
    },
}


@ToolService.register("git_commit_push", COMMIT_PUSH_DEFINITION)
async def git_commit_push(params: dict, context: dict) -> dict:
    """Stage all, commit, and push."""
    token = _get_git_token(context)

    directory = params["directory"]
    try:
        repo_path = _safe_workspace_path(directory, context)
    except ValueError as e:
        return {"error": str(e)}

    if not repo_path.exists():
        return {"error": f"Directory not found: {directory}"}

    try:
        await asyncio.to_thread(
            _commit_push_sync,
            repo_path,
            params["message"],
            params.get("branch"),
        )
    except Exception as e:
        return {"error": _redact_token(str(e), token)}
    return {"committed": True, "pushed": True, "directory": directory}


# --- git_create_branch ---

CREATE_BRANCH_DEFINITION = {
    "name": "git_create_branch",
    "description": "Create and checkout a new git branch in a cloned repository.",
    "parameters": {
        "type": "object",
        "properties": {
            "directory": {"type": "string", "description": "Directory name within workspace"},
            "branch": {"type": "string", "description": "New branch name to create"},
            "base": {
                "type": "string",
                "description": "Base branch to create from (default: current branch)",
            },
        },
        "required": ["directory", "branch"],
    },
}


@ToolService.register("git_create_branch", CREATE_BRANCH_DEFINITION)
async def git_create_branch(params: dict, context: dict) -> dict:
    """Create and checkout a new branch."""
    directory = params["directory"]
    try:
        repo_path = _safe_workspace_path(directory, context)
    except ValueError as e:
        return {"error": str(e)}

    if not repo_path.exists():
        return {"error": f"Directory not found: {directory}"}

    try:
        active = await asyncio.to_thread(
            _create_branch_sync,
            repo_path,
            params["branch"],
            params.get("base"),
        )
    except Exception as e:
        return {"error": str(e)}
    return {"branch": active, "directory": directory}


# --- git_diff ---

DIFF_DEFINITION = {
    "name": "git_diff",
    "description": "Show staged and unstaged changes in a cloned repository. Use before committing to review changes.",
    "parameters": {
        "type": "object",
        "properties": {
            "directory": {"type": "string", "description": "Directory name within workspace"},
        },
        "required": ["directory"],
    },
}


@ToolService.register("git_diff", DIFF_DEFINITION)
async def git_diff(params: dict, context: dict) -> dict:
    """Show git diff."""
    directory = params["directory"]
    try:
        repo_path = _safe_workspace_path(directory, context)
    except ValueError as e:
        return {"error": str(e)}

    if not repo_path.exists():
        return {"error": f"Directory not found: {directory}"}

    try:
        output = await asyncio.to_thread(_diff_sync, repo_path)
    except Exception as e:
        return {"error": str(e)}
    return {"diff": output}
