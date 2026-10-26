# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""File operations tools — read, write, delete files and manage directories in the workspace."""

import shutil
from pathlib import Path

import aiofiles

from team.config import get_settings
from team.services.tool_service import ToolService

MAX_FILE_SIZE = 100 * 1024  # 100 KB


def _safe_path(relative: str, context: dict | None = None) -> Path:
    """Resolve a relative path within the workspace directory.

    Uses task-scoped workspace from context when available,
    falls back to global workspace_dir setting.

    Raises ValueError if the resolved path escapes the workspace.
    """
    if context and "workspace_dir" in context:
        workspace = Path(context["workspace_dir"]).resolve()
    else:
        workspace = Path(get_settings().workspace_dir).resolve()
    full = (workspace / relative).resolve()
    if not str(full).startswith(str(workspace)):
        raise ValueError(f"Path traversal blocked: {relative}")
    return full


# --- file_read ---

READ_DEFINITION = {
    "name": "file_read",
    "description": "Read the contents of a file in the workspace.",
    "parameters": {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Relative path within workspace"},
        },
        "required": ["path"],
    },
}


@ToolService.register("file_read", READ_DEFINITION)
async def file_read(params: dict, context: dict) -> dict:
    """Read a file from the workspace."""
    try:
        full_path = _safe_path(params["path"], context)
    except ValueError as e:
        return {"error": str(e)}

    if not full_path.exists():
        return {"error": f"File not found: {params['path']}"}

    if full_path.stat().st_size > MAX_FILE_SIZE:
        return {"error": f"File too large (max {MAX_FILE_SIZE} bytes)"}

    async with aiofiles.open(full_path) as f:
        content = await f.read()
    return {"content": content, "path": params["path"]}


# --- file_write ---

WRITE_DEFINITION = {
    "name": "file_write",
    "description": "Write content to a file in the workspace (creates parent directories).",
    "parameters": {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Relative path within workspace"},
            "content": {"type": "string", "description": "File content to write"},
        },
        "required": ["path", "content"],
    },
}


@ToolService.register("file_write", WRITE_DEFINITION)
async def file_write(params: dict, context: dict) -> dict:
    """Write content to a file in the workspace."""
    try:
        full_path = _safe_path(params["path"], context)
    except ValueError as e:
        return {"error": str(e)}

    full_path.parent.mkdir(parents=True, exist_ok=True)
    async with aiofiles.open(full_path, "w") as f:
        await f.write(params["content"])
    return {"written": True, "path": params["path"]}


# --- file_delete ---

DELETE_DEFINITION = {
    "name": "file_delete",
    "description": "Delete a file from the workspace.",
    "parameters": {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Relative path within workspace"},
        },
        "required": ["path"],
    },
}


@ToolService.register("file_delete", DELETE_DEFINITION)
async def file_delete(params: dict, context: dict) -> dict:
    """Delete a file from the workspace."""
    try:
        full_path = _safe_path(params["path"], context)
    except ValueError as e:
        return {"error": str(e)}

    if not full_path.exists():
        return {"error": f"File not found: {params['path']}"}

    full_path.unlink()
    return {"deleted": True, "path": params["path"]}


# --- dir_mkdir ---

MKDIR_DEFINITION = {
    "name": "dir_mkdir",
    "description": "Create a directory (and parents) in the workspace.",
    "parameters": {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Relative directory path within workspace"},
        },
        "required": ["path"],
    },
}


@ToolService.register("dir_mkdir", MKDIR_DEFINITION)
async def dir_mkdir(params: dict, context: dict) -> dict:
    """Create a directory in the workspace."""
    try:
        full_path = _safe_path(params["path"], context)
    except ValueError as e:
        return {"error": str(e)}

    full_path.mkdir(parents=True, exist_ok=True)
    return {"created": True, "path": params["path"]}


# --- dir_rmdir ---

RMDIR_DEFINITION = {
    "name": "dir_rmdir",
    "description": "Remove a directory from the workspace. Use recursive=true to remove non-empty directories.",
    "parameters": {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Relative directory path within workspace"},
            "recursive": {
                "type": "boolean",
                "description": "Remove directory and all contents recursively",
                "default": False,
            },
        },
        "required": ["path"],
    },
}


@ToolService.register("dir_rmdir", RMDIR_DEFINITION)
async def dir_rmdir(params: dict, context: dict) -> dict:
    """Remove a directory from the workspace."""
    try:
        full_path = _safe_path(params["path"], context)
    except ValueError as e:
        return {"error": str(e)}

    if not full_path.exists():
        return {"error": f"Directory not found: {params['path']}"}

    if not full_path.is_dir():
        return {"error": f"Not a directory: {params['path']}"}

    if params.get("recursive", False):
        shutil.rmtree(full_path)
    else:
        try:
            full_path.rmdir()
        except OSError:
            return {
                "error": f"Directory not empty: {params['path']}. Use recursive=true to remove."
            }

    return {"removed": True, "path": params["path"]}


# --- dir_list ---

DIR_LIST_DEFINITION = {
    "name": "dir_list",
    "description": "List contents of a directory in the workspace.",
    "parameters": {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "Relative directory path within workspace (default: root)",
                "default": ".",
            },
        },
    },
}


@ToolService.register("dir_list", DIR_LIST_DEFINITION)
async def dir_list(params: dict, context: dict) -> dict:
    """List contents of a directory in the workspace."""
    rel_path = params.get("path", ".")
    try:
        full_path = _safe_path(rel_path, context)
    except ValueError as e:
        return {"error": str(e)}

    if not full_path.exists():
        return {"error": f"Directory not found: {rel_path}"}

    if not full_path.is_dir():
        return {"error": f"Not a directory: {rel_path}"}

    entries = []
    for item in sorted(full_path.iterdir()):
        entries.append(
            {
                "name": item.name,
                "type": "directory" if item.is_dir() else "file",
            }
        )
    return {"path": rel_path, "entries": entries}
