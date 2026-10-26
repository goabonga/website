# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for file operations tools."""

from unittest.mock import patch

import team.services.tools  # noqa: F401
from team.services.tool_service import ToolService


def _ctx():
    return {}


class TestFileRead:
    async def test_read_file(self, tmp_path):
        test_file = tmp_path / "hello.txt"
        test_file.write_text("Hello, World!")

        with patch("team.services.tools.file_ops.get_settings") as m:
            m.return_value.workspace_dir = str(tmp_path)
            result = await ToolService._registry["file_read"][0](
                {"path": "hello.txt"},
                _ctx(),
            )
        assert result["content"] == "Hello, World!"
        assert result["path"] == "hello.txt"

    async def test_read_file_not_found(self, tmp_path):
        with patch("team.services.tools.file_ops.get_settings") as m:
            m.return_value.workspace_dir = str(tmp_path)
            result = await ToolService._registry["file_read"][0](
                {"path": "missing.txt"},
                _ctx(),
            )
        assert "error" in result
        assert "not found" in result["error"].lower()

    async def test_read_file_too_large(self, tmp_path):
        large_file = tmp_path / "big.bin"
        large_file.write_bytes(b"x" * (100 * 1024 + 1))

        with patch("team.services.tools.file_ops.get_settings") as m:
            m.return_value.workspace_dir = str(tmp_path)
            result = await ToolService._registry["file_read"][0](
                {"path": "big.bin"},
                _ctx(),
            )
        assert "error" in result
        assert "too large" in result["error"].lower()

    async def test_read_path_traversal(self, tmp_path):
        with patch("team.services.tools.file_ops.get_settings") as m:
            m.return_value.workspace_dir = str(tmp_path)
            result = await ToolService._registry["file_read"][0](
                {"path": "../../etc/passwd"},
                _ctx(),
            )
        assert "error" in result
        assert "traversal" in result["error"].lower()


class TestFileWrite:
    async def test_write_file(self, tmp_path):
        with patch("team.services.tools.file_ops.get_settings") as m:
            m.return_value.workspace_dir = str(tmp_path)
            result = await ToolService._registry["file_write"][0](
                {"path": "output.txt", "content": "Test content"},
                _ctx(),
            )
        assert result["written"] is True
        assert (tmp_path / "output.txt").read_text() == "Test content"

    async def test_write_creates_parent_dirs(self, tmp_path):
        with patch("team.services.tools.file_ops.get_settings") as m:
            m.return_value.workspace_dir = str(tmp_path)
            result = await ToolService._registry["file_write"][0](
                {"path": "sub/dir/file.txt", "content": "Nested"},
                _ctx(),
            )
        assert result["written"] is True
        assert (tmp_path / "sub" / "dir" / "file.txt").read_text() == "Nested"

    async def test_write_path_traversal(self, tmp_path):
        with patch("team.services.tools.file_ops.get_settings") as m:
            m.return_value.workspace_dir = str(tmp_path)
            result = await ToolService._registry["file_write"][0](
                {"path": "../../evil.txt", "content": "bad"},
                _ctx(),
            )
        assert "error" in result
        assert "traversal" in result["error"].lower()


class TestFileDelete:
    async def test_delete_file(self, tmp_path):
        target = tmp_path / "to_delete.txt"
        target.write_text("bye")

        with patch("team.services.tools.file_ops.get_settings") as m:
            m.return_value.workspace_dir = str(tmp_path)
            result = await ToolService._registry["file_delete"][0](
                {"path": "to_delete.txt"},
                _ctx(),
            )
        assert result["deleted"] is True
        assert not target.exists()

    async def test_delete_file_not_found(self, tmp_path):
        with patch("team.services.tools.file_ops.get_settings") as m:
            m.return_value.workspace_dir = str(tmp_path)
            result = await ToolService._registry["file_delete"][0](
                {"path": "nope.txt"},
                _ctx(),
            )
        assert "error" in result
        assert "not found" in result["error"].lower()

    async def test_delete_path_traversal(self, tmp_path):
        with patch("team.services.tools.file_ops.get_settings") as m:
            m.return_value.workspace_dir = str(tmp_path)
            result = await ToolService._registry["file_delete"][0](
                {"path": "../../../etc/passwd"},
                _ctx(),
            )
        assert "error" in result
        assert "traversal" in result["error"].lower()


class TestDirMkdir:
    async def test_mkdir_creates_directory(self, tmp_path):
        with patch("team.services.tools.file_ops.get_settings") as m:
            m.return_value.workspace_dir = str(tmp_path)
            result = await ToolService._registry["dir_mkdir"][0](
                {"path": "new_dir"},
                _ctx(),
            )
        assert result["created"] is True
        assert (tmp_path / "new_dir").is_dir()

    async def test_mkdir_creates_nested(self, tmp_path):
        with patch("team.services.tools.file_ops.get_settings") as m:
            m.return_value.workspace_dir = str(tmp_path)
            result = await ToolService._registry["dir_mkdir"][0](
                {"path": "a/b/c"},
                _ctx(),
            )
        assert result["created"] is True
        assert (tmp_path / "a" / "b" / "c").is_dir()

    async def test_mkdir_existing_is_ok(self, tmp_path):
        (tmp_path / "exists").mkdir()
        with patch("team.services.tools.file_ops.get_settings") as m:
            m.return_value.workspace_dir = str(tmp_path)
            result = await ToolService._registry["dir_mkdir"][0](
                {"path": "exists"},
                _ctx(),
            )
        assert result["created"] is True

    async def test_mkdir_path_traversal(self, tmp_path):
        with patch("team.services.tools.file_ops.get_settings") as m:
            m.return_value.workspace_dir = str(tmp_path)
            result = await ToolService._registry["dir_mkdir"][0](
                {"path": "../../evil"},
                _ctx(),
            )
        assert "error" in result
        assert "traversal" in result["error"].lower()


class TestDirRmdir:
    async def test_rmdir_empty(self, tmp_path):
        (tmp_path / "empty").mkdir()
        with patch("team.services.tools.file_ops.get_settings") as m:
            m.return_value.workspace_dir = str(tmp_path)
            result = await ToolService._registry["dir_rmdir"][0](
                {"path": "empty"},
                _ctx(),
            )
        assert result["removed"] is True
        assert not (tmp_path / "empty").exists()

    async def test_rmdir_non_empty_fails(self, tmp_path):
        d = tmp_path / "notempty"
        d.mkdir()
        (d / "file.txt").write_text("data")
        with patch("team.services.tools.file_ops.get_settings") as m:
            m.return_value.workspace_dir = str(tmp_path)
            result = await ToolService._registry["dir_rmdir"][0](
                {"path": "notempty"},
                _ctx(),
            )
        assert "error" in result
        assert "not empty" in result["error"].lower()

    async def test_rmdir_recursive(self, tmp_path):
        d = tmp_path / "deep"
        (d / "sub").mkdir(parents=True)
        (d / "sub" / "file.txt").write_text("nested")
        with patch("team.services.tools.file_ops.get_settings") as m:
            m.return_value.workspace_dir = str(tmp_path)
            result = await ToolService._registry["dir_rmdir"][0](
                {"path": "deep", "recursive": True},
                _ctx(),
            )
        assert result["removed"] is True
        assert not (tmp_path / "deep").exists()

    async def test_rmdir_not_found(self, tmp_path):
        with patch("team.services.tools.file_ops.get_settings") as m:
            m.return_value.workspace_dir = str(tmp_path)
            result = await ToolService._registry["dir_rmdir"][0](
                {"path": "nope"},
                _ctx(),
            )
        assert "error" in result
        assert "not found" in result["error"].lower()

    async def test_rmdir_not_a_directory(self, tmp_path):
        (tmp_path / "afile.txt").write_text("hi")
        with patch("team.services.tools.file_ops.get_settings") as m:
            m.return_value.workspace_dir = str(tmp_path)
            result = await ToolService._registry["dir_rmdir"][0](
                {"path": "afile.txt"},
                _ctx(),
            )
        assert "error" in result
        assert "not a directory" in result["error"].lower()

    async def test_rmdir_path_traversal(self, tmp_path):
        with patch("team.services.tools.file_ops.get_settings") as m:
            m.return_value.workspace_dir = str(tmp_path)
            result = await ToolService._registry["dir_rmdir"][0](
                {"path": "../../etc"},
                _ctx(),
            )
        assert "error" in result
        assert "traversal" in result["error"].lower()


class TestDirList:
    async def test_list_root(self, tmp_path):
        (tmp_path / "file.txt").write_text("hi")
        (tmp_path / "subdir").mkdir()
        with patch("team.services.tools.file_ops.get_settings") as m:
            m.return_value.workspace_dir = str(tmp_path)
            result = await ToolService._registry["dir_list"][0](
                {},
                _ctx(),
            )
        assert result["path"] == "."
        names = {e["name"] for e in result["entries"]}
        assert "file.txt" in names
        assert "subdir" in names
        types = {e["name"]: e["type"] for e in result["entries"]}
        assert types["file.txt"] == "file"
        assert types["subdir"] == "directory"

    async def test_list_subdir(self, tmp_path):
        d = tmp_path / "project"
        d.mkdir()
        (d / "main.py").write_text("print()")
        with patch("team.services.tools.file_ops.get_settings") as m:
            m.return_value.workspace_dir = str(tmp_path)
            result = await ToolService._registry["dir_list"][0](
                {"path": "project"},
                _ctx(),
            )
        assert result["path"] == "project"
        assert len(result["entries"]) == 1
        assert result["entries"][0]["name"] == "main.py"

    async def test_list_not_found(self, tmp_path):
        with patch("team.services.tools.file_ops.get_settings") as m:
            m.return_value.workspace_dir = str(tmp_path)
            result = await ToolService._registry["dir_list"][0](
                {"path": "missing"},
                _ctx(),
            )
        assert "error" in result
        assert "not found" in result["error"].lower()

    async def test_list_not_a_directory(self, tmp_path):
        (tmp_path / "afile.txt").write_text("hi")
        with patch("team.services.tools.file_ops.get_settings") as m:
            m.return_value.workspace_dir = str(tmp_path)
            result = await ToolService._registry["dir_list"][0](
                {"path": "afile.txt"},
                _ctx(),
            )
        assert "error" in result
        assert "not a directory" in result["error"].lower()

    async def test_list_path_traversal(self, tmp_path):
        with patch("team.services.tools.file_ops.get_settings") as m:
            m.return_value.workspace_dir = str(tmp_path)
            result = await ToolService._registry["dir_list"][0](
                {"path": "../../etc"},
                _ctx(),
            )
        assert "error" in result
        assert "traversal" in result["error"].lower()


class TestContextWorkspace:
    """Tests verifying tools use workspace_dir from context when present."""

    async def test_read_uses_context_workspace(self, tmp_path):
        test_file = tmp_path / "hello.txt"
        test_file.write_text("Hello!")
        ctx = {"workspace_dir": str(tmp_path)}
        result = await ToolService._registry["file_read"][0](
            {"path": "hello.txt"},
            ctx,
        )
        assert result["content"] == "Hello!"

    async def test_read_context_path_traversal(self, tmp_path):
        ctx = {"workspace_dir": str(tmp_path)}
        result = await ToolService._registry["file_read"][0](
            {"path": "../../etc/passwd"},
            ctx,
        )
        assert "traversal" in result["error"].lower()

    async def test_write_uses_context_workspace(self, tmp_path):
        ctx = {"workspace_dir": str(tmp_path)}
        result = await ToolService._registry["file_write"][0](
            {"path": "out.txt", "content": "data"},
            ctx,
        )
        assert result["written"] is True
        assert (tmp_path / "out.txt").read_text() == "data"

    async def test_delete_uses_context_workspace(self, tmp_path):
        target = tmp_path / "del.txt"
        target.write_text("bye")
        ctx = {"workspace_dir": str(tmp_path)}
        result = await ToolService._registry["file_delete"][0](
            {"path": "del.txt"},
            ctx,
        )
        assert result["deleted"] is True
        assert not target.exists()
