# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Unit tests for web document chunking helpers."""

from knowledge.routes.web.documents import (
    CHUNK_MODE_MARKDOWN_SECTIONS,
    CHUNK_MODE_SPLIT_5,
    CHUNK_MODE_SPLIT_10,
    _chunk_content,
    _display_content_size,
    _split_even_chunks,
    _split_markdown_sections,
)


def test_chunk_markdown_sections():
    content = "# One\nalpha\n\n## Two\nbeta\n\n### Three\ngamma"
    chunks = _chunk_content(content, CHUNK_MODE_MARKDOWN_SECTIONS)
    assert len(chunks) == 3
    assert chunks[0].startswith("# One")
    assert chunks[1].startswith("## Two")
    assert chunks[2].startswith("### Three")


def test_chunk_split_5():
    content = " ".join(f"w{i}" for i in range(100))
    chunks = _chunk_content(content, CHUNK_MODE_SPLIT_5)
    assert len(chunks) == 5
    assert all(chunk.strip() for chunk in chunks)


def test_chunk_split_10():
    content = " ".join(f"w{i}" for i in range(100))
    chunks = _chunk_content(content, CHUNK_MODE_SPLIT_10)
    assert len(chunks) == 10
    assert all(chunk.strip() for chunk in chunks)


def test_chunk_markdown_empty_content():
    assert _split_markdown_sections("   ") == []


def test_chunk_markdown_no_heading_returns_single_block():
    content = "plain text without headings"
    assert _split_markdown_sections(content) == [content]


def test_chunk_even_empty_content():
    assert _split_even_chunks("   ", 5) == []


def test_chunk_even_parts_leq_one():
    assert _split_even_chunks("alpha beta", 1) == ["alpha beta"]


def test_chunk_even_no_words_after_split():
    class WeirdStr(str):
        def strip(self, chars=None):
            return self

        def split(self, sep=None, maxsplit=-1):
            return []

    assert _split_even_chunks(WeirdStr("x"), 5) == ["x"]


def test_chunk_unknown_mode_falls_back_to_whole_content():
    assert _chunk_content("abc", "unknown") == ["abc"]


def test_chunk_markdown_skips_empty_chunk_with_mocked_regex(monkeypatch):
    class FakeMatch:
        def __init__(self, start_pos: int):
            self._start = start_pos

        def start(self):
            return self._start

    class FakeRegex:
        def finditer(self, _text):
            # First slice 0:0 => empty chunk (skipped), second yields full text.
            return [FakeMatch(0), FakeMatch(0)]

    monkeypatch.setattr(
        "knowledge.routes.web.documents.re.compile", lambda *args, **kwargs: FakeRegex()
    )

    chunks = _split_markdown_sections("# H")
    assert chunks == ["# H"]


def test_chunk_even_skips_empty_piece_with_weird_split():
    class WeirdStr(str):
        def strip(self, chars=None):
            return self

        def split(self, sep=None, maxsplit=-1):
            # Produces an empty first joined chunk when chunk_size == 1.
            return ["", "word"]

    chunks = _split_even_chunks(WeirdStr("x"), 2)
    assert chunks == ["word"]


def test_display_content_size_fallback_when_size_is_zero_and_content_missing():
    class Doc:
        content_size = 0
        content = None

    assert _display_content_size(Doc()) == 0
