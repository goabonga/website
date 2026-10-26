# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Application configuration."""

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()


def get_credential(name: str, default: str = "") -> str:
    """Read a secret from systemd credentials or environment.

    Systemd credentials are stored in $CREDENTIALS_DIRECTORY when the service
    is started with LoadCredentialEncrypted. Falls back to environment variables
    for local development.
    """
    creds_dir = os.environ.get("CREDENTIALS_DIRECTORY")
    if creds_dir:
        cred_file = Path(creds_dir) / name
        if cred_file.exists():
            return cred_file.read_text().strip()
    return os.environ.get(name, default)


class Config:
    """Application configuration."""

    # AudioSocket server settings
    AUDIOSOCKET_HOST: str = os.getenv("AUDIOSOCKET_HOST", "127.0.0.1")
    AUDIOSOCKET_PORT: int = int(os.getenv("AUDIOSOCKET_PORT", "9092"))

    # OpenAI settings (from systemd-creds or env)
    OPENAI_API_KEY: str = get_credential("OPENAI_API_KEY", "")
    OPENAI_MODEL: str = os.getenv("OPENAI_MODEL", "gpt-4o-realtime-preview-2024-12-17")
    OPENAI_VOICE: str = os.getenv("OPENAI_VOICE", "alloy")
    OPENAI_SYSTEM_PROMPT: str = os.getenv(
        "OPENAI_SYSTEM_PROMPT",
        "You are a helpful phone assistant. Keep responses brief and conversational. Speak in French.",
    )

    # Database (PostgreSQL with pgvector)
    DATABASE_URL: str = os.getenv("DATABASE_URL", "")

    # RAG (Retrieval-Augmented Generation) settings
    RAG_ENABLED: bool = os.getenv("RAG_ENABLED", "false").lower() == "true"
    RAG_EMBEDDING_MODEL: str = os.getenv("RAG_EMBEDDING_MODEL", "text-embedding-3-small")
    RAG_SIMILARITY_THRESHOLD: float = float(os.getenv("RAG_SIMILARITY_THRESHOLD", "0.7"))
    RAG_MAX_RESULTS: int = int(os.getenv("RAG_MAX_RESULTS", "3"))

    # Logging
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")


config = Config()
