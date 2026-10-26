# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""AI-powered knowledge entry generation service using OpenAI."""

import json
import logging

from openai import AsyncOpenAI

from internal.config import settings

logger = logging.getLogger(__name__)

GENERATION_SYSTEM_PROMPT = """You are a knowledge base content generator. Your task is to analyze the provided text and generate a set of question-answer pairs that would be useful for a RAG (Retrieval-Augmented Generation) system.

For each entry you generate:
1. The QUESTION should be a natural question that a user might ask
2. The ANSWER should be comprehensive but concise, directly answering the question based on the source text
3. Include relevant METADATA with tags and categories

Output your response as a JSON array with the following structure:
[
  {
    "question": "What is...",
    "answer": "The answer based on the source text...",
    "metadata": {
      "tags": ["tag1", "tag2"],
      "category": "category_name",
      "source": "generated"
    }
  }
]

Important guidelines:
- Generate diverse questions covering different aspects of the text
- Questions should be standalone and understandable without context
- Answers should be self-contained and accurate
- Use the source text as the basis, don't invent information
- Keep answers informative but not overly long
- Generate exactly the number of entries requested"""


class KnowledgeGeneratorService:
    """Service for generating knowledge entries using OpenAI."""

    def __init__(self, model: str = "gpt-4o-mini") -> None:
        self.client = AsyncOpenAI(api_key=settings.openai_api_key)
        self.model = model

    async def generate_entries(
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
            "Generating %d knowledge entries using %s",
            num_entries,
            self.model,
        )

        try:
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": GENERATION_SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0.7,
                response_format={"type": "json_object"},
            )

            content: str = (
                response.content
                if hasattr(response, "content")
                else response.choices[0].message.content
            ) or ""
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

            logger.info("Generated %d entries", len(entries))
            return entries

        except json.JSONDecodeError as e:
            logger.error("Failed to parse OpenAI response as JSON: %s", e)
            return []
        except Exception as e:
            logger.error("Failed to generate entries: %s", e)
            raise
