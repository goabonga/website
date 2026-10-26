# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""User agent parsing service."""

from dataclasses import dataclass

from analytics.logging import get_logger

logger = get_logger(__name__)


@dataclass
class DeviceInfo:
    """Parsed device information."""

    device_type: str | None = None  # mobile, tablet, desktop, bot
    browser: str | None = None
    browser_version: str | None = None
    os: str | None = None
    os_version: str | None = None
    is_bot: bool = False


class UserAgentService:
    """Service for parsing user agent strings."""

    def __init__(self) -> None:
        self._parser = None

    def _get_parser(self):
        """Lazy load the user agent parser."""
        if self._parser is not None:
            return self._parser

        try:
            from user_agents import parse

            self._parser = parse
            return self._parser
        except ImportError:
            logger.warning("user-agents package not installed")
            return None

    def parse(self, user_agent: str | None) -> DeviceInfo:
        """Parse a user agent string.

        Args:
            user_agent: User agent string to parse.

        Returns:
            DeviceInfo with parsed information.
        """
        if not user_agent:
            return DeviceInfo()

        parser = self._get_parser()
        if parser is None:
            return self._basic_parse(user_agent)

        try:
            ua = parser(user_agent)

            # Determine device type
            if ua.is_bot:
                device_type = "bot"
            elif ua.is_mobile:
                device_type = "mobile"
            elif ua.is_tablet:
                device_type = "tablet"
            elif ua.is_pc:
                device_type = "desktop"
            else:
                device_type = "other"

            return DeviceInfo(
                device_type=device_type,
                browser=ua.browser.family if ua.browser.family != "Other" else None,
                browser_version=ua.browser.version_string or None,
                os=ua.os.family if ua.os.family != "Other" else None,
                os_version=ua.os.version_string or None,
                is_bot=ua.is_bot,
            )
        except Exception as e:
            logger.debug(f"Failed to parse user agent: {e}")
            return self._basic_parse(user_agent)

    def _basic_parse(self, user_agent: str) -> DeviceInfo:
        """Basic user agent parsing without external library."""
        ua_lower = user_agent.lower()

        # Check for bots
        bot_keywords = ["bot", "crawler", "spider", "scraper", "curl", "wget"]
        is_bot = any(kw in ua_lower for kw in bot_keywords)

        if is_bot:
            return DeviceInfo(device_type="bot", is_bot=True)

        # Check for mobile
        mobile_keywords = ["mobile", "android", "iphone", "ipod"]
        tablet_keywords = ["tablet", "ipad"]

        if any(kw in ua_lower for kw in tablet_keywords):
            device_type = "tablet"
        elif any(kw in ua_lower for kw in mobile_keywords):
            device_type = "mobile"
        else:
            device_type = "desktop"

        # Basic browser detection
        browser = None
        if "chrome" in ua_lower and "edg" not in ua_lower:
            browser = "Chrome"
        elif "firefox" in ua_lower:
            browser = "Firefox"
        elif "safari" in ua_lower and "chrome" not in ua_lower:
            browser = "Safari"
        elif "edg" in ua_lower:
            browser = "Edge"

        # Basic OS detection
        os_name = None
        if "windows" in ua_lower:
            os_name = "Windows"
        elif "mac os" in ua_lower or "macos" in ua_lower:
            os_name = "macOS"
        elif "linux" in ua_lower:
            os_name = "Linux"
        elif "android" in ua_lower:
            os_name = "Android"
        elif "ios" in ua_lower or "iphone" in ua_lower or "ipad" in ua_lower:
            os_name = "iOS"

        return DeviceInfo(
            device_type=device_type,
            browser=browser,
            os=os_name,
            is_bot=False,
        )


# Singleton instance
useragent_service = UserAgentService()
