# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Application configuration."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    app_name: str = "mta-sts"
    log_level: str = "INFO"

    # MTA-STS (RFC 8461)
    mta_sts_mode: str = "enforce"
    mta_sts_mx: str = "mail.goabonga.com"
    mta_sts_max_age: int = 86400

    @property
    def mx_hosts(self) -> list[str]:
        """Parse MX hosts from comma-separated string."""
        return [mx.strip() for mx in self.mta_sts_mx.split(",") if mx.strip()]


settings = Settings()
