# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Chunked upload API."""

import pytest
from apt_server.config import settings
from debfactory import build_deb

CHUNK = 64


@pytest.fixture(autouse=True)
def _repository(repo_root, monkeypatch):
    monkeypatch.setattr(settings, "upload_max_size", 10_000_000)
    return repo_root


def init_payload(raw: bytes, **overrides) -> dict:
    chunks = [raw[i : i + CHUNK] for i in range(0, len(raw), CHUNK)]
    return {
        "filename": "demo.deb",
        "total_size": len(raw),
        "total_chunks": len(chunks),
        "suite": "stable",
        "component": "main",
        "visibility": "private",
        **overrides,
    }


async def send_chunks(http, upload_id: str, raw: bytes) -> None:
    for index, start in enumerate(range(0, len(raw), CHUNK)):
        response = await http.post(
            f"/api/upload/{upload_id}/chunk",
            params={"index": index},
            files={"chunk": ("chunk", raw[start : start + CHUNK])},
        )
        assert response.status_code == 200


async def start(http, raw: bytes, **overrides) -> str:
    response = await http.post("/api/upload/init", json=init_payload(raw, **overrides))
    assert response.status_code == 200, response.text
    return response.json()["upload_id"]


async def test_init_requires_a_caller(http, login_caller) -> None:
    login_caller(None)

    response = await http.post("/api/upload/init", json=init_payload(build_deb()))

    assert response.status_code == 401


async def test_init_requires_a_write_scope(http, login_caller) -> None:
    login_caller("alice", ["apt:read"])

    response = await http.post("/api/upload/init", json=init_payload(build_deb()))

    assert response.status_code == 403


async def test_init_skips_the_scope_check_for_web_sessions(http, login_caller) -> None:
    login_caller("alice", [], is_session=True)

    response = await http.post("/api/upload/init", json=init_payload(build_deb()))

    assert response.status_code == 200


async def test_init_returns_the_session_and_chunk_size(http, login_caller) -> None:
    login_caller("alice", ["apt:write"])

    response = await http.post("/api/upload/init", json=init_payload(build_deb()))

    assert response.json()["chunk_size"] == settings.upload_chunk_size
    assert response.json()["upload_id"]


async def test_init_rejects_oversized_uploads(http, login_caller, monkeypatch) -> None:
    login_caller("alice", ["apt:write"])
    monkeypatch.setattr(settings, "upload_max_size", 10)

    response = await http.post("/api/upload/init", json=init_payload(build_deb()))

    assert response.status_code == 400
    assert "too large" in response.json()["detail"]


async def test_full_upload_creates_the_package(http, login_caller, repo_root) -> None:
    login_caller("alice", ["apt:write"])
    raw = build_deb("big", "2.0")
    upload_id = await start(http, raw, visibility="public")
    await send_chunks(http, upload_id, raw)

    response = await http.post(f"/api/upload/{upload_id}/complete")

    assert response.status_code == 200
    body = response.json()
    assert (body["name"], body["version"], body["owner_id"]) == ("big", "2.0", "alice")
    assert body["visibility"] == "public"
    assert (repo_root / body["filename"]).is_file()
    assert not (repo_root / ".uploads" / upload_id).exists()


async def test_unknown_visibility_falls_back_to_private(http, login_caller) -> None:
    login_caller("alice", ["apt:write"])
    raw = build_deb()
    upload_id = await start(http, raw, visibility="weird")
    await send_chunks(http, upload_id, raw)

    response = await http.post(f"/api/upload/{upload_id}/complete")

    assert response.json()["visibility"] == "private"


async def test_complete_with_missing_chunks_is_rejected(http, login_caller) -> None:
    login_caller("alice", ["apt:write"])
    raw = build_deb()
    upload_id = await start(http, raw)

    response = await http.post(f"/api/upload/{upload_id}/complete")

    assert response.status_code == 400
    assert "missing chunks" in response.json()["detail"]


async def test_complete_reports_invalid_archives_and_cleans_up(http, login_caller, repo_root):
    login_caller("alice", ["apt:write"])
    raw = b"x" * 100
    upload_id = await start(http, raw)
    await send_chunks(http, upload_id, raw)

    response = await http.post(f"/api/upload/{upload_id}/complete")

    assert response.status_code == 400
    assert not (repo_root / ".uploads" / upload_id).exists()


async def test_complete_reports_conflicts(http, login_caller) -> None:
    login_caller("alice", ["apt:write"])
    raw = build_deb()
    for expected in (200, 409):
        upload_id = await start(http, raw)
        await send_chunks(http, upload_id, raw)
        assert (await http.post(f"/api/upload/{upload_id}/complete")).status_code == expected


async def test_chunk_errors(http, login_caller) -> None:
    login_caller("alice", ["apt:write"])
    raw = build_deb()
    upload_id = await start(http, raw)
    url = f"/api/upload/{upload_id}/chunk"

    out_of_range = await http.post(url, params={"index": 999}, files={"chunk": ("c", b"x")})
    negative = await http.post(url, params={"index": -1}, files={"chunk": ("c", b"x")})
    await http.post(url, params={"index": 0}, files={"chunk": ("c", b"x")})
    duplicate = await http.post(url, params={"index": 0}, files={"chunk": ("c", b"x")})
    unknown = await http.post(
        "/api/upload/missing/chunk", params={"index": 0}, files={"chunk": ("c", b"x")}
    )

    assert out_of_range.status_code == 400
    assert negative.status_code == 422
    assert duplicate.status_code == 400
    assert unknown.status_code == 404


async def test_chunk_response_reports_progress(http, login_caller) -> None:
    login_caller("alice", ["apt:write"])
    raw = build_deb()
    upload_id = await start(http, raw)

    response = await http.post(
        f"/api/upload/{upload_id}/chunk", params={"index": 0}, files={"chunk": ("c", raw[:CHUNK])}
    )

    assert response.json() == {
        "upload_id": upload_id,
        "index": 0,
        "received": 1,
        "total": init_payload(raw)["total_chunks"],
    }


async def test_other_users_cannot_touch_an_upload(http, login_caller) -> None:
    login_caller("alice", ["apt:write"])
    raw = build_deb()
    upload_id = await start(http, raw)
    login_caller("mallory", ["apt:write"])

    chunk = await http.post(
        f"/api/upload/{upload_id}/chunk", params={"index": 0}, files={"chunk": ("c", b"x")}
    )
    complete = await http.post(f"/api/upload/{upload_id}/complete")
    cancel = await http.delete(f"/api/upload/{upload_id}")

    assert [chunk.status_code, complete.status_code, cancel.status_code] == [403, 403, 403]


async def test_unknown_sessions_are_not_found(http, login_caller) -> None:
    login_caller("alice", ["apt:write"])

    assert (await http.post("/api/upload/missing/complete")).status_code == 404
    assert (await http.delete("/api/upload/missing")).status_code == 404


async def test_cancel_removes_the_session(http, login_caller, repo_root) -> None:
    login_caller("alice", ["apt:write"])
    upload_id = await start(http, build_deb())

    response = await http.delete(f"/api/upload/{upload_id}")

    assert response.status_code == 204
    assert not (repo_root / ".uploads" / upload_id).exists()


async def test_endpoints_require_a_caller(http, login_caller) -> None:
    login_caller(None)

    assert (await http.post("/api/upload/x/complete")).status_code == 401
    assert (await http.delete("/api/upload/x")).status_code == 401
