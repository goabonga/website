# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Embedding generation service using OpenAI text-embedding-3-small."""

import logging

import openai

from team.config import settings

logger = logging.getLogger(__name__)

EMBEDDING_MODEL = "text-embedding-3-small"
EMBEDDING_DIMENSIONS = 1536


async def generate_embedding(text: str) -> list[float]:
    """Generate an embedding vector for the given text.

    Uses OpenAI text-embedding-3-small (1536 dimensions).
    Returns a zero vector if the API key is not configured.
    """
    if not settings.openai_api_key:
        logger.warning("OPENAI_API_KEY not configured, returning zero embedding")
        return [0.0] * EMBEDDING_DIMENSIONS

    client = openai.AsyncOpenAI(api_key=settings.openai_api_key)
    try:
        response = await client.embeddings.create(
            model=EMBEDDING_MODEL,
            input=text,
            dimensions=EMBEDDING_DIMENSIONS,
        )
        return response.data[0].embedding
    finally:
        await client.close()


async def generate_embeddings_batch(texts: list[str]) -> list[list[float]]:
    """Generate embeddings for multiple texts in a single API call.

    Returns zero vectors if the API key is not configured.
    """
    if not texts:
        return []

    if not settings.openai_api_key:
        logger.warning("OPENAI_API_KEY not configured, returning zero embeddings")
        return [[0.0] * EMBEDDING_DIMENSIONS for _ in texts]

    client = openai.AsyncOpenAI(api_key=settings.openai_api_key)
    try:
        response = await client.embeddings.create(
            model=EMBEDDING_MODEL,
            input=texts,
            dimensions=EMBEDDING_DIMENSIONS,
        )
        return [item.embedding for item in response.data]
    finally:
        await client.close()
