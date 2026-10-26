# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Application configuration."""

import os

from dotenv import load_dotenv

load_dotenv()


class Config:
    """Application configuration."""

    # AudioSocket server settings
    AUDIOSOCKET_HOST: str = os.getenv("AUDIOSOCKET_HOST", "127.0.0.1")
    AUDIOSOCKET_PORT: int = int(os.getenv("AUDIOSOCKET_PORT", "9092"))

    # Logging
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")


config = Config()
