# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for analytics.services.geoip module."""

from unittest.mock import MagicMock, patch

from analytics.services.geoip import GeoIPService, GeoLocation


class TestGeoLocation:
    """Tests for GeoLocation dataclass."""

    def test_defaults(self):
        geo = GeoLocation()
        assert geo.country is None
        assert geo.city is None

    def test_with_values(self):
        geo = GeoLocation(country="FR", city="Paris")
        assert geo.country == "FR"
        assert geo.city == "Paris"


class TestGeoIPService:
    """Tests for GeoIPService."""

    def test_disabled_returns_empty(self):
        with patch("analytics.services.geoip.settings") as mock_settings:
            mock_settings.geoip_enabled = False
            mock_settings.geoip_database_path = "/nonexistent"
            service = GeoIPService()
        result = service.lookup("8.8.8.8")
        assert result == GeoLocation()

    def test_private_ip_returns_empty(self):
        with patch("analytics.services.geoip.settings") as mock_settings:
            mock_settings.geoip_enabled = True
            mock_settings.geoip_database_path = "/nonexistent"
            service = GeoIPService()
            service._reader = MagicMock()
        result = service.lookup("127.0.0.1")
        assert result == GeoLocation()

    def test_private_ip_192(self):
        with patch("analytics.services.geoip.settings") as mock_settings:
            mock_settings.geoip_enabled = True
            mock_settings.geoip_database_path = "/nonexistent"
            service = GeoIPService()
            service._reader = MagicMock()
        result = service.lookup("192.168.1.1")
        assert result == GeoLocation()

    def test_invalid_ip_returns_empty(self):
        with patch("analytics.services.geoip.settings") as mock_settings:
            mock_settings.geoip_enabled = True
            mock_settings.geoip_database_path = "/nonexistent"
            service = GeoIPService()
            service._reader = MagicMock()
        result = service.lookup("invalid")
        assert result == GeoLocation()

    def test_missing_database_disables(self):
        with patch("analytics.services.geoip.settings") as mock_settings:
            mock_settings.geoip_enabled = True
            mock_settings.geoip_database_path = "/nonexistent/GeoLite2-City.mmdb"
            service = GeoIPService()
        reader = service._get_reader()
        assert reader is None
        assert service._enabled is False

    def test_close_with_reader(self):
        with patch("analytics.services.geoip.settings") as mock_settings:
            mock_settings.geoip_enabled = False
            mock_settings.geoip_database_path = "/nonexistent"
            service = GeoIPService()
        mock_reader = MagicMock()
        service._reader = mock_reader
        service.close()
        mock_reader.close.assert_called_once()
        assert service._reader is None

    def test_close_without_reader(self):
        with patch("analytics.services.geoip.settings") as mock_settings:
            mock_settings.geoip_enabled = False
            mock_settings.geoip_database_path = "/nonexistent"
            service = GeoIPService()
        service.close()  # Should not raise

    def test_lookup_with_reader_exception(self):
        with patch("analytics.services.geoip.settings") as mock_settings:
            mock_settings.geoip_enabled = True
            mock_settings.geoip_database_path = "/nonexistent"
            service = GeoIPService()
        mock_reader = MagicMock()
        mock_reader.city.side_effect = Exception("Not found")
        service._reader = mock_reader
        result = service.lookup("8.8.8.8")
        assert result == GeoLocation()

    def test_successful_lookup(self):
        with patch("analytics.services.geoip.settings") as mock_settings:
            mock_settings.geoip_enabled = True
            mock_settings.geoip_database_path = "/nonexistent"
            service = GeoIPService()
        mock_reader = MagicMock()
        mock_response = MagicMock()
        mock_response.country.iso_code = "US"
        mock_response.city.name = "Mountain View"
        mock_reader.city.return_value = mock_response
        service._reader = mock_reader
        result = service.lookup("8.8.8.8")
        assert result.country == "US"
        assert result.city == "Mountain View"


class TestGeoIPServiceGetReader:
    """Tests for GeoIPService._get_reader success and error paths (lines 41-54)."""

    def test_get_reader_successful_load(self):
        """When geoip2 is importable and database exists, return a reader."""
        with patch("analytics.services.geoip.settings") as mock_settings:
            mock_settings.geoip_enabled = True
            mock_settings.geoip_database_path = "/tmp/test.mmdb"
            service = GeoIPService()

        mock_reader_instance = MagicMock(name="reader_instance")
        mock_geoip2_database = MagicMock(name="geoip2.database")
        mock_geoip2_database.Reader.return_value = mock_reader_instance
        mock_geoip2 = MagicMock(name="geoip2")
        mock_geoip2.database = mock_geoip2_database

        with patch("pathlib.Path.exists", return_value=True):
            import sys

            with patch.dict(
                sys.modules,
                {
                    "geoip2": mock_geoip2,
                    "geoip2.database": mock_geoip2_database,
                },
            ):
                reader = service._get_reader()

        assert reader is mock_reader_instance
        assert service._reader is mock_reader_instance

    def test_get_reader_import_error(self):
        """When geoip2 is not installable, return None and disable."""
        with patch("analytics.services.geoip.settings") as mock_settings:
            mock_settings.geoip_enabled = True
            mock_settings.geoip_database_path = "/tmp/test.mmdb"
            service = GeoIPService()

        original_import = __import__

        def import_raiser(name, *args, **kwargs):
            if name == "geoip2.database" or name == "geoip2":
                raise ImportError("No module named 'geoip2'")
            return original_import(name, *args, **kwargs)

        with (
            patch("pathlib.Path.exists", return_value=True),
            patch("builtins.__import__", side_effect=import_raiser),
        ):
            reader = service._get_reader()

        assert reader is None
        assert service._enabled is False

    def test_get_reader_generic_exception(self):
        """When Reader() raises a generic exception, return None and disable."""
        with patch("analytics.services.geoip.settings") as mock_settings:
            mock_settings.geoip_enabled = True
            mock_settings.geoip_database_path = "/tmp/test.mmdb"
            service = GeoIPService()

        mock_geoip2_database = MagicMock(name="geoip2.database")
        mock_geoip2_database.Reader.side_effect = Exception("corrupt database")
        mock_geoip2 = MagicMock(name="geoip2")
        mock_geoip2.database = mock_geoip2_database

        import sys

        with (
            patch("pathlib.Path.exists", return_value=True),
            patch.dict(
                sys.modules,
                {
                    "geoip2": mock_geoip2,
                    "geoip2.database": mock_geoip2_database,
                },
            ),
        ):
            reader = service._get_reader()

        assert reader is None
        assert service._enabled is False

    def test_get_reader_returns_cached_reader(self):
        """When _reader is already set, return it without reloading."""
        with patch("analytics.services.geoip.settings") as mock_settings:
            mock_settings.geoip_enabled = True
            mock_settings.geoip_database_path = "/tmp/test.mmdb"
            service = GeoIPService()

        sentinel_reader = MagicMock(name="cached_reader")
        service._reader = sentinel_reader
        result = service._get_reader()
        assert result is sentinel_reader
