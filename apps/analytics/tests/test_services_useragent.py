# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for analytics.services.useragent module."""

import sys
from unittest.mock import MagicMock, patch

from analytics.services.useragent import DeviceInfo, UserAgentService


class TestDeviceInfo:
    """Tests for DeviceInfo dataclass."""

    def test_defaults(self):
        info = DeviceInfo()
        assert info.device_type is None
        assert info.browser is None
        assert info.browser_version is None
        assert info.os is None
        assert info.os_version is None
        assert info.is_bot is False


class TestUserAgentServiceBasicParse:
    """Tests for UserAgentService._basic_parse method."""

    def setup_method(self):
        self.service = UserAgentService()

    def test_none_user_agent(self):
        result = self.service.parse(None)
        assert result == DeviceInfo()

    def test_empty_user_agent(self):
        result = self.service.parse("")
        assert result == DeviceInfo()

    def test_bot_detection(self):
        result = self.service._basic_parse("Googlebot/2.1 (+http://www.google.com/bot.html)")
        assert result.device_type == "bot"
        assert result.is_bot is True

    def test_curl_is_bot(self):
        result = self.service._basic_parse("curl/7.68.0")
        assert result.device_type == "bot"
        assert result.is_bot is True

    def test_mobile_detection(self):
        result = self.service._basic_parse("Mozilla/5.0 (iPhone; CPU iPhone OS 14_0 like Mac OS X)")
        assert result.device_type == "mobile"

    def test_tablet_detection(self):
        result = self.service._basic_parse("Mozilla/5.0 (iPad; CPU OS 14_0 like Mac OS X)")
        assert result.device_type == "tablet"

    def test_desktop_detection(self):
        result = self.service._basic_parse(
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        )
        assert result.device_type == "desktop"

    def test_chrome_browser(self):
        result = self.service._basic_parse(
            "Mozilla/5.0 (Windows NT 10.0) Chrome/91.0.4472.124 Safari/537.36"
        )
        assert result.browser == "Chrome"

    def test_firefox_browser(self):
        result = self.service._basic_parse(
            "Mozilla/5.0 (Windows NT 10.0; rv:89.0) Gecko/20100101 Firefox/89.0"
        )
        assert result.browser == "Firefox"

    def test_safari_browser(self):
        result = self.service._basic_parse(
            "Mozilla/5.0 (Macintosh) AppleWebKit/605.1.15 Safari/605.1.15"
        )
        assert result.browser == "Safari"

    def test_edge_browser(self):
        result = self.service._basic_parse(
            "Mozilla/5.0 (Windows NT 10.0) Chrome/91.0 Edg/91.0.864.59"
        )
        assert result.browser == "Edge"

    def test_windows_os(self):
        result = self.service._basic_parse("Mozilla/5.0 (Windows NT 10.0)")
        assert result.os == "Windows"

    def test_macos_detection(self):
        result = self.service._basic_parse("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15)")
        assert result.os == "macOS"

    def test_linux_os(self):
        result = self.service._basic_parse("Mozilla/5.0 (X11; Linux x86_64)")
        assert result.os == "Linux"

    def test_android_os(self):
        # Note: basic parser checks "linux" before "android", so
        # Android user agents (which contain "Linux") return "Linux"
        result = self.service._basic_parse("Mozilla/5.0 (Linux; Android 11)")
        assert result.os == "Linux"

    def test_android_only_os(self):
        result = self.service._basic_parse("Mozilla/5.0 (Android 11)")
        assert result.os == "Android"

    def test_ios_detection(self):
        result = self.service._basic_parse("Mozilla/5.0 (iPhone; CPU iPhone OS 14_0)")
        assert result.os == "iOS"


class TestGetParser:
    """Tests for UserAgentService._get_parser method."""

    def test_get_parser_returns_cached(self):
        """When _parser is already set, return it without reloading."""
        service = UserAgentService()
        sentinel = lambda ua: None  # noqa: E731
        service._parser = sentinel
        assert service._get_parser() is sentinel

    def test_get_parser_handles_import_error(self):
        """When user_agents is not importable, return None."""
        service = UserAgentService()
        service._parser = None

        original_import = (
            __builtins__.__import__ if hasattr(__builtins__, "__import__") else __import__
        )

        def import_raiser(name, *args, **kwargs):
            if name == "user_agents":
                raise ImportError("No module named 'user_agents'")
            return original_import(name, *args, **kwargs)

        with patch("builtins.__import__", side_effect=import_raiser):
            result = service._get_parser()
        assert result is None

    def test_get_parser_loads_library_successfully(self):
        """When user_agents is importable, cache and return parse function."""
        service = UserAgentService()
        service._parser = None

        mock_parse = MagicMock(name="parse_function")
        mock_user_agents = MagicMock()
        mock_user_agents.parse = mock_parse

        with patch.dict(sys.modules, {"user_agents": mock_user_agents}):
            result = service._get_parser()

        assert result is mock_parse
        assert service._parser is mock_parse


class TestUserAgentServiceAdvancedParse:
    """Tests for UserAgentService.parse with the advanced parser path."""

    def _make_mock_ua(
        self,
        is_bot=False,
        is_mobile=False,
        is_tablet=False,
        is_pc=False,
        browser_family="Chrome",
        browser_version="91.0",
        os_family="Windows",
        os_version="10",
    ):
        """Helper to create a mock parsed user agent object."""
        mock_ua = MagicMock()
        mock_ua.is_bot = is_bot
        mock_ua.is_mobile = is_mobile
        mock_ua.is_tablet = is_tablet
        mock_ua.is_pc = is_pc
        mock_ua.browser.family = browser_family
        mock_ua.browser.version_string = browser_version
        mock_ua.os.family = os_family
        mock_ua.os.version_string = os_version
        return mock_ua

    def test_parse_with_advanced_bot(self):
        """Bot user agent returns device_type='bot' and is_bot=True."""
        service = UserAgentService()
        mock_ua = self._make_mock_ua(
            is_bot=True,
            browser_family="Googlebot",
            browser_version="2.1",
            os_family="Other",
            os_version="",
        )
        service._parser = lambda ua: mock_ua
        result = service.parse("Googlebot/2.1 (+http://www.google.com/bot.html)")
        assert result.device_type == "bot"
        assert result.is_bot is True
        assert result.browser == "Googlebot"

    def test_parse_with_advanced_desktop_chrome(self):
        """Desktop Chrome user agent is correctly identified."""
        service = UserAgentService()
        mock_ua = self._make_mock_ua(
            is_pc=True,
            browser_family="Chrome",
            browser_version="91.0.4472",
            os_family="Windows",
            os_version="10",
        )
        service._parser = lambda ua: mock_ua
        result = service.parse(
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
        )
        assert result.device_type == "desktop"
        assert result.browser == "Chrome"
        assert result.browser_version == "91.0.4472"
        assert result.os == "Windows"
        assert result.os_version == "10"

    def test_parse_with_advanced_mobile(self):
        """Mobile user agent returns device_type='mobile'."""
        service = UserAgentService()
        mock_ua = self._make_mock_ua(
            is_mobile=True,
            browser_family="Mobile Safari",
            browser_version="14.0",
            os_family="iOS",
            os_version="14.0",
        )
        service._parser = lambda ua: mock_ua
        result = service.parse("Mozilla/5.0 (iPhone; CPU iPhone OS 14_0 like Mac OS X)")
        assert result.device_type == "mobile"
        assert result.os == "iOS"

    def test_parse_with_advanced_tablet(self):
        """Tablet user agent returns device_type='tablet'."""
        service = UserAgentService()
        mock_ua = self._make_mock_ua(
            is_tablet=True,
            browser_family="Mobile Safari",
            browser_version="14.0",
            os_family="iOS",
            os_version="14.0",
        )
        service._parser = lambda ua: mock_ua
        result = service.parse("Mozilla/5.0 (iPad; CPU OS 14_0 like Mac OS X)")
        assert result.device_type == "tablet"

    def test_parse_with_other_device(self):
        """When no device category matches, return device_type='other'."""
        service = UserAgentService()
        mock_ua = self._make_mock_ua(
            is_bot=False,
            is_mobile=False,
            is_tablet=False,
            is_pc=False,
            browser_family="Other",
            browser_version="",
            os_family="Other",
            os_version="",
        )
        service._parser = lambda ua: mock_ua
        result = service.parse("SomeUnknownUA")
        assert result.device_type == "other"
        assert result.browser is None
        assert result.os is None

    def test_parse_browser_other_returns_none(self):
        """When browser family is 'Other', browser field should be None."""
        service = UserAgentService()
        mock_ua = self._make_mock_ua(
            is_pc=True,
            browser_family="Other",
            browser_version="",
            os_family="Windows",
            os_version="10",
        )
        service._parser = lambda ua: mock_ua
        result = service.parse("Mozilla/5.0")
        assert result.browser is None
        assert result.browser_version is None

    def test_parse_os_other_returns_none(self):
        """When OS family is 'Other', os field should be None."""
        service = UserAgentService()
        mock_ua = self._make_mock_ua(
            is_pc=True,
            browser_family="Chrome",
            browser_version="91.0",
            os_family="Other",
            os_version="",
        )
        service._parser = lambda ua: mock_ua
        result = service.parse("Mozilla/5.0")
        assert result.os is None
        assert result.os_version is None

    def test_parse_exception_falls_back_to_basic(self):
        """When the advanced parser raises, fall back to _basic_parse."""
        service = UserAgentService()
        service._parser = MagicMock(side_effect=Exception("parse failed"))
        result = service.parse("Mozilla/5.0 (Windows NT 10.0)")
        # Basic parse would detect "windows" and classify as desktop
        assert result.device_type == "desktop"
        assert result.os == "Windows"

    def test_parse_none_parser_falls_back_to_basic(self):
        """When _get_parser returns None, use _basic_parse."""
        service = UserAgentService()
        service._parser = None

        original_import = (
            __builtins__.__import__ if hasattr(__builtins__, "__import__") else __import__
        )

        def import_raiser(name, *args, **kwargs):
            if name == "user_agents":
                raise ImportError("No module named 'user_agents'")
            return original_import(name, *args, **kwargs)

        with patch("builtins.__import__", side_effect=import_raiser):
            result = service.parse("Mozilla/5.0 (Windows NT 10.0)")
        assert result.device_type == "desktop"
        assert result.os == "Windows"
