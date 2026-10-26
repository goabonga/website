# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""GeoIP lookup service using MaxMind GeoLite2."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import geoip2.database

from analytics.config import settings
from analytics.logging import get_logger

logger = get_logger(__name__)


@dataclass
class GeoLocation:
    """Geolocation result."""

    country: str | None = None
    city: str | None = None


class GeoIPService:
    """Service for IP geolocation using MaxMind GeoLite2."""

    def __init__(self) -> None:
        self._reader: geoip2.database.Reader | None = None
        self._enabled = settings.geoip_enabled
        self._database_path = settings.geoip_database_path

    def _get_reader(self):
        """Lazy load the GeoIP reader."""
        if self._reader is not None:
            return self._reader

        if not self._enabled:
            return None

        if not Path(self._database_path).exists():
            logger.warning(f"GeoIP database not found at {self._database_path}")
            self._enabled = False
            return None

        try:
            import geoip2.database

            self._reader = geoip2.database.Reader(self._database_path)
            logger.info(f"GeoIP database loaded from {self._database_path}")
            return self._reader
        except ImportError:
            logger.warning("geoip2 package not installed, GeoIP disabled")
            self._enabled = False
            return None
        except Exception as e:
            logger.error(f"Failed to load GeoIP database: {e}")
            self._enabled = False
            return None

    def lookup(self, ip_address: str) -> GeoLocation:
        """Look up geolocation for an IP address.

        Args:
            ip_address: IP address to look up.

        Returns:
            GeoLocation with country and city if found.
        """
        reader = self._get_reader()
        if reader is None:
            return GeoLocation()

        # Skip private/local addresses
        if self._is_private_ip(ip_address):
            return GeoLocation()

        try:
            response = reader.city(ip_address)
            return GeoLocation(
                country=response.country.iso_code,
                city=response.city.name,
            )
        except Exception:
            # IP not found or other error
            return GeoLocation()

    def _is_private_ip(self, ip_address: str) -> bool:
        """Check if an IP address is private/local."""
        try:
            import ipaddress

            ip = ipaddress.ip_address(ip_address)
            return ip.is_private or ip.is_loopback or ip.is_link_local
        except ValueError:
            return True

    def close(self) -> None:
        """Close the GeoIP database reader."""
        if self._reader is not None:
            self._reader.close()
            self._reader = None


# Singleton instance
geoip_service = GeoIPService()
