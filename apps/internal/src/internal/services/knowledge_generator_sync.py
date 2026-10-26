# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Sync AI-powered knowledge entry generation service using OpenAI.

This is the synchronous version of KnowledgeGeneratorService, used by Celery workers.
"""

import json
import logging

from openai import OpenAI

from internal.config import settings
from internal.services.knowledge_generator import GENERATION_SYSTEM_PROMPT

logger = logging.getLogger(__name__)


class SyncKnowledgeGeneratorService:
    """Sync service for generating knowledge entries using OpenAI."""

    def __init__(self, model: str = "gpt-4o-mini") -> None:
        self.client = OpenAI(api_key=settings.openai_api_key)
        self.model = model

    def generate_entries(
        self,
        source_text: str,
        num_entries: int = 5,
        context: str | None = None,
    ) -> list[dict]:
        """Generate knowledge entries from source text.

        Args:
            source_text: The text to generate entries from
            num_entries: Number of entries to generate (1-20)
            context: Optional additional context or instructions

        Returns:
            List of generated entries with question, answer, and metadata
        """
        num_entries = max(1, min(50, num_entries))

        user_prompt = f"""Please analyze the following text and generate exactly {num_entries} question-answer pairs for a knowledge base.

SOURCE TEXT:
---
{source_text}
---
"""

        if context:
            user_prompt += f"""
ADDITIONAL CONTEXT/INSTRUCTIONS:
{context}
"""

        user_prompt += f"""
Generate exactly {num_entries} entries in JSON format."""

        logger.info(
            "Generating %d knowledge entries using %s (sync)",
            num_entries,
            self.model,
        )

        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": GENERATION_SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0.7,
                response_format={"type": "json_object"},
            )

            content: str = response.choices[0].message.content or ""
            result = json.loads(content)

            # Handle both array and object with entries key
            if isinstance(result, list):
                entries = result
            elif isinstance(result, dict) and "entries" in result:
                entries = result["entries"]
            else:
                # Try to find an array in the response
                for _key, value in result.items():
                    if isinstance(value, list):
                        entries = value
                        break
                else:
                    logger.error("Unexpected response format: %s", result)
                    return []

            logger.info("Generated %d entries (sync)", len(entries))
            return entries

        except json.JSONDecodeError as e:
            logger.error("Failed to parse OpenAI response as JSON: %s", e)
            return []
        except Exception as e:
            logger.error("Failed to generate entries: %s", e)
            raise
