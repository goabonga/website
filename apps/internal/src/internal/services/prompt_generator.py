# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""AI-powered system prompt generation service using OpenAI."""

import json
import logging
import re

from openai import AsyncOpenAI

from internal.config import settings

logger = logging.getLogger(__name__)

GENERATION_SYSTEM_PROMPT = """You are an expert AI prompt engineer. Your task is to create high-quality system prompts for AI assistants based on the user's requirements.

When creating a system prompt:
1. Define clear behavior and personality traits
2. Set appropriate boundaries and constraints
3. Include specific instructions for common scenarios
4. Maintain consistency with the requested tone
5. Make the prompt actionable and specific

Output your response as a JSON object with the following structure:
{
  "name": "Short descriptive name (2-4 words)",
  "slug": "kebab-case-identifier",
  "description": "Brief description of the prompt's purpose (1-2 sentences)",
  "content": "The full system prompt content..."
}

Important guidelines:
- The content should be comprehensive but not overly long (300-800 words ideal)
- Use clear, direct language
- Include specific guidance for handling edge cases
- The slug should be lowercase, using hyphens between words
- Make the prompt professional and well-structured"""


class PromptGeneratorService:
    """Service for generating system prompts using OpenAI."""

    def __init__(self, model: str = "gpt-4o-mini") -> None:
        self.client = AsyncOpenAI(api_key=settings.openai_api_key)
        self.model = model

    async def generate_prompt(
        self,
        description: str,
        tone: str = "professional",
        focus_areas: str | None = None,
        constraints: str | None = None,
    ) -> dict:
        """Generate a system prompt from a description.

        Args:
            description: Description of the desired AI assistant behavior
            tone: Desired tone (professional, friendly, casual, formal, technical)
            focus_areas: Specific areas the assistant should focus on
            constraints: Any constraints or limitations

        Returns:
            Dict with name, slug, description, and content
        """
        user_prompt = f"""Please create a system prompt for an AI assistant with the following requirements:

DESCRIPTION:
{description}

TONE: {tone}
"""

        if focus_areas:
            user_prompt += f"""
FOCUS AREAS:
{focus_areas}
"""

        if constraints:
            user_prompt += f"""
CONSTRAINTS/LIMITATIONS:
{constraints}
"""

        user_prompt += """
Generate the system prompt as a JSON object."""

        logger.info("Generating system prompt using %s", self.model)

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

            content = response.choices[0].message.content or ""
            result = json.loads(content)

            # Validate required fields
            if not all(k in result for k in ["name", "slug", "description", "content"]):
                logger.error("Generated prompt missing required fields")
                return {}

            # Sanitize slug
            result["slug"] = self._sanitize_slug(result["slug"])

            logger.info("Generated prompt: %s", result["name"])
            return result

        except json.JSONDecodeError as e:
            logger.error("Failed to parse OpenAI response as JSON: %s", e)
            return {}
        except Exception as e:
            logger.error("Failed to generate prompt: %s", e)
            raise

    def _sanitize_slug(self, slug: str) -> str:
        """Sanitize a slug to be URL-safe."""
        # Convert to lowercase
        slug = slug.lower()
        # Replace spaces and underscores with hyphens
        slug = re.sub(r"[\s_]+", "-", slug)
        # Remove any characters that aren't alphanumeric or hyphens
        slug = re.sub(r"[^a-z0-9-]", "", slug)
        # Remove multiple consecutive hyphens
        slug = re.sub(r"-+", "-", slug)
        # Remove leading/trailing hyphens
        slug = slug.strip("-")
        return slug or "generated-prompt"
