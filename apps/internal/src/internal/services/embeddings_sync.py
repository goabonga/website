# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Sync embedding generation service using OpenAI.

This is the synchronous version of EmbeddingService, used by Celery workers.
"""

import logging

from openai import OpenAI

from internal.config import settings

logger = logging.getLogger(__name__)


class SyncEmbeddingService:
    """Sync service for generating text embeddings using OpenAI."""

    def __init__(self, model: str | None = None) -> None:
        self.client = OpenAI(api_key=settings.openai_api_key)
        self.model = model or settings.rag_embedding_model

    def generate(self, text: str) -> list[float]:
        """Generate embedding for a single text."""
        response = self.client.embeddings.create(
            model=self.model,
            input=text,
        )
        return response.data[0].embedding
