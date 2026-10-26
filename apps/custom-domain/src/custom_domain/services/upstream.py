# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Upstream targets: where nginx forwards the requests of a domain.

A target is either a Unix socket (an absolute path, optionally written
``unix:/path``) or a TCP address ``host:port`` (``[v6-address]:port`` for IPv6).
Targets end up in generated nginx configuration, so they are validated strictly:
only the characters of a path, a host name or an IP address are accepted.
"""

import ipaddress
import re
from dataclasses import dataclass

UNIX = "unix"
TCP = "tcp"

MAX_TARGET_LENGTH = 500  # size of the ``upstream_target`` column

_SOCKET_PATH_RE = re.compile(r"^/[A-Za-z0-9._@+/-]+$")
_HOST_RE = re.compile(
    r"^(?=.{1,253}$)[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?"
    r"(?:\.[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?)*$"
)
_MAX_PORT = 65535


class InvalidUpstreamError(ValueError):
    """The text is not a valid upstream target."""


@dataclass(frozen=True)
class Upstream:
    """A parsed upstream target."""

    kind: str
    address: str

    @property
    def nginx_server(self) -> str:
        """The value of the ``server`` directive of an nginx ``upstream`` block."""
        return f"unix:{self.address}" if self.kind == UNIX else self.address


def parse_upstream(target: str) -> Upstream:
    """Validate an upstream target.

    Args:
        target: ``/run/app.sock``, ``unix:/run/app.sock``, ``app.internal:8000``,
            ``10.0.0.5:8000`` or ``[::1]:8000``

    Raises:
        InvalidUpstreamError: If the target is neither a socket path nor a host and port
    """
    value = target.strip()
    if not value or len(value) > MAX_TARGET_LENGTH:
        raise InvalidUpstreamError("Upstream target is empty or too long")

    if value.startswith("unix:"):
        value = value[len("unix:") :]

    if value.startswith("/"):
        if not _SOCKET_PATH_RE.fullmatch(value) or ".." in value.split("/"):
            raise InvalidUpstreamError(f"Invalid Unix socket path: {target!r}")
        return Upstream(UNIX, value)

    host, separator, port = value.rpartition(":")
    if not separator or not port.isascii() or not port.isdigit():
        raise InvalidUpstreamError(
            f"Upstream must be an absolute socket path or host:port, got {target!r}"
        )
    if not 0 < int(port) <= _MAX_PORT:
        raise InvalidUpstreamError(f"Invalid upstream port: {port}")

    if host.startswith("[") and host.endswith("]"):
        try:
            ipaddress.IPv6Address(host[1:-1])
        except ValueError as error:
            raise InvalidUpstreamError(f"Invalid IPv6 address: {host}") from error
    elif not _HOST_RE.fullmatch(host):
        raise InvalidUpstreamError(f"Invalid upstream host: {host!r}")

    return Upstream(TCP, f"{host}:{int(port)}")
