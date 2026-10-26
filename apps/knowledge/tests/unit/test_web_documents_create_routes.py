# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Targeted unit tests for create_document route branches."""

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from fastapi.responses import HTMLResponse

from knowledge.auth.models import User, WebAuthContext
from knowledge.models.enums import PlanType
from knowledge.routes.web.documents import create_document


class DummyUpload:
    def __init__(self, filename: str, data: bytes):
        self.filename = filename
        self._data = data

    async def read(self) -> bytes:
        return self._data


def _make_auth_context():
    user = User(
        id=uuid4(),
        email="test@example.com",
        name="Test User",
        scopes=["documents:write"],
    )
    tenant = MagicMock()
    tenant.id = uuid4()
    tenant.name = "Test Org"
    tenant.plan = PlanType.FREE
    tenant.is_active = True
    member = MagicMock()
    member.is_admin = True
    member.is_owner = True
    member.organization_id = tenant.id
    return WebAuthContext(user=user, tenant=tenant, tenant_member=member)


def _make_result(scalar_one_or_none=None, scalars_all=None):
    result = MagicMock()
    result.scalar_one_or_none.return_value = scalar_one_or_none
    result.scalars.return_value.all.return_value = scalars_all or []
    return result


@pytest.mark.asyncio
@patch("knowledge.routes.web.documents.templates")
@patch("knowledge.routes.web.documents.QuotaService")
async def test_create_document_empty_content_returns_400(mock_quota_cls, mock_templates):
    request = MagicMock()
    auth = _make_auth_context()
    db = AsyncMock()
    collection = MagicMock()
    collection.id = uuid4()
    db.execute = AsyncMock(
        side_effect=[
            _make_result(scalar_one_or_none=collection),  # collection lookup
            _make_result(scalars_all=[]),  # tenant switcher lookup in _get_common_context
        ]
    )

    quota = mock_quota_cls.return_value
    quota.enforce_document_quota = AsyncMock()
    quota.enforce_storage_quota = AsyncMock()
    mock_templates.TemplateResponse.return_value = HTMLResponse("bad", status_code=400)

    response = await create_document(
        request=request,
        collection_id=uuid4(),
        content="",
        source_type="",
        source_ref="",
        file=None,
        enable_chunking=False,
        chunk_mode="",
        db=db,
        auth_result=auth,
    )

    assert response.status_code == 400
    assert mock_templates.TemplateResponse.called


@pytest.mark.asyncio
@patch("knowledge.routes.web.documents.DocumentService")
@patch("knowledge.routes.web.documents.QuotaService")
async def test_create_document_file_decode_error_sets_defaults(mock_quota_cls, mock_doc_cls):
    request = MagicMock()
    auth = _make_auth_context()
    db = AsyncMock()
    collection = MagicMock()
    collection.id = uuid4()
    db.execute = AsyncMock(return_value=_make_result(scalar_one_or_none=collection))

    quota = mock_quota_cls.return_value
    quota.enforce_document_quota = AsyncMock()
    quota.enforce_storage_quota = AsyncMock()

    doc_service = mock_doc_cls.return_value
    doc_service.create = AsyncMock()

    file = DummyUpload(filename="bad.txt", data=b"\xff\xfe\xfa")
    response = await create_document(
        request=request,
        collection_id=uuid4(),
        content="",
        source_type="",
        source_ref="",
        file=file,
        enable_chunking=False,
        chunk_mode="",
        db=db,
        auth_result=auth,
    )

    assert response.status_code == 302
    assert doc_service.create.await_count == 1
    created = doc_service.create.await_args_list[0].args[1]
    assert created.source_type == "file"
    assert created.source_ref == "bad.txt"


@pytest.mark.asyncio
@patch("knowledge.routes.web.documents._chunk_content", return_value=[])
@patch("knowledge.routes.web.documents.DocumentService")
@patch("knowledge.routes.web.documents.QuotaService")
async def test_create_document_chunk_empty_fallback(
    mock_quota_cls, mock_doc_cls, _mock_chunk_content
):
    request = MagicMock()
    auth = _make_auth_context()
    db = AsyncMock()
    collection = MagicMock()
    collection.id = uuid4()
    db.execute = AsyncMock(return_value=_make_result(scalar_one_or_none=collection))

    quota = mock_quota_cls.return_value
    quota.enforce_document_quota = AsyncMock()
    quota.enforce_storage_quota = AsyncMock()

    doc_service = mock_doc_cls.return_value
    doc_service.create = AsyncMock()

    response = await create_document(
        request=request,
        collection_id=uuid4(),
        content="hello world",
        source_type="manual",
        source_ref="ref",
        file=None,
        enable_chunking=True,
        chunk_mode="split_5",
        db=db,
        auth_result=auth,
    )

    assert response.status_code == 302
    assert doc_service.create.await_count == 1
    created = doc_service.create.await_args_list[0].args[1]
    assert created.content == "hello world"


@pytest.mark.asyncio
@patch("knowledge.routes.web.documents.DocumentService")
@patch("knowledge.routes.web.documents.QuotaService")
async def test_create_document_file_keeps_explicit_source_fields(mock_quota_cls, mock_doc_cls):
    request = MagicMock()
    auth = _make_auth_context()
    db = AsyncMock()
    collection = MagicMock()
    collection.id = uuid4()
    db.execute = AsyncMock(return_value=_make_result(scalar_one_or_none=collection))

    quota = mock_quota_cls.return_value
    quota.enforce_document_quota = AsyncMock()
    quota.enforce_storage_quota = AsyncMock()

    doc_service = mock_doc_cls.return_value
    doc_service.create = AsyncMock()

    file = DummyUpload(filename="ignored.txt", data=b"hello")
    response = await create_document(
        request=request,
        collection_id=uuid4(),
        content="",
        source_type="manual",
        source_ref="custom-ref",
        file=file,
        enable_chunking=False,
        chunk_mode="",
        db=db,
        auth_result=auth,
    )

    assert response.status_code == 302
    created = doc_service.create.await_args_list[0].args[1]
    assert created.source_type == "manual"
    assert created.source_ref == "custom-ref"
