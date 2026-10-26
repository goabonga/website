# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""RAG module with knowledge base and embedding support."""

from backend.rag.embeddings import EmbeddingService
from backend.rag.knowledge_base import KnowledgeBase

__all__ = ["EmbeddingService", "KnowledgeBase"]
