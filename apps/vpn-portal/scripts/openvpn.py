#!/usr/bin/env python3

# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""OpenVPN client-connect/disconnect hook script.

Called by OpenVPN server to validate certificates, record connections,
and record disconnections via the VPN Portal internal API.

Authentication: OAuth2 client_credentials flow against the auth server.
Token caching: File-based (configurable, default /var/run/vpn-portal/token.json).

Usage in OpenVPN server.conf:
    client-connect /opt/vpn-portal/scripts/openvpn.py --connect
    client-disconnect /opt/vpn-portal/scripts/openvpn.py --disconnect
    tls-verify /opt/vpn-portal/scripts/openvpn.py --reneg
    reneg-sec 300

Environment variables:
    OPENVPN_OAUTH2_CLIENT_ID       OAuth2 client ID
    OPENVPN_OAUTH2_CLIENT_SECRET   OAuth2 client secret (or via systemd-creds / CREDENTIALS_DIRECTORY)
    OPENVPN_OAUTH2_TOKEN_URL       Token endpoint (e.g. https://auth.example.com/oauth2/token)
    OPENVPN_API_BASE_URL           VPN Portal API base URL (default: http://127.0.0.1:8000)
    OPENVPN_TOKEN_CACHE_PATH       Token cache file (default: /var/run/vpn-portal/token.json)
    OPENVPN_OAUTH2_SCOPE           Scope to request (default: vpn:server)
    OPENVPN_MANAGEMENT_HOST        Management interface host (default: 127.0.0.1)
    OPENVPN_MANAGEMENT_PORT        Management interface port (default: 7505)
"""

from __future__ import annotations

import argparse
import json
import logging
import logging.handlers
import os
import socket
import sys
import time
from pathlib import Path

import httpx

# ---------------------------------------------------------------------------
# Configuration (from environment / systemd credentials)
# ---------------------------------------------------------------------------


def _get_credential(name: str, default: str = "") -> str:
    """Read a secret from systemd credentials directory or environment.

    Systemd's LoadCredential= / SetCredential= exposes secrets as files
    under $CREDENTIALS_DIRECTORY.  This is the preferred way to pass
    secrets to long-running services (no /proc/*/environ leak).
    """
    creds_dir = os.environ.get("CREDENTIALS_DIRECTORY")
    if creds_dir:
        cred_file = Path(creds_dir) / name
        if cred_file.exists():
            return cred_file.read_text().strip()
    return os.environ.get(name, default)


CLIENT_ID = os.environ.get("OPENVPN_OAUTH2_CLIENT_ID", "")
CLIENT_SECRET = _get_credential("OPENVPN_OAUTH2_CLIENT_SECRET")
TOKEN_URL = os.environ.get("OPENVPN_OAUTH2_TOKEN_URL", "")
API_BASE_URL = os.environ.get("OPENVPN_API_BASE_URL", "http://127.0.0.1:8000")
TOKEN_CACHE_PATH = os.environ.get("OPENVPN_TOKEN_CACHE_PATH", "/var/run/vpn-portal/token.json")
OAUTH2_SCOPE = os.environ.get("OPENVPN_OAUTH2_SCOPE", "vpn:server")

# OpenVPN management interface (for killing clients on revoked certs)
MANAGEMENT_HOST = os.environ.get("OPENVPN_MANAGEMENT_HOST", "127.0.0.1")
MANAGEMENT_PORT = int(os.environ.get("OPENVPN_MANAGEMENT_PORT", "7505"))

TOKEN_EXPIRY_MARGIN = 30  # seconds

logger = logging.getLogger("openvpn-hook")


# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------


def setup_logging() -> None:
    """Configure logging to syslog and stderr."""
    logger.setLevel(logging.DEBUG)

    # Syslog (daemon facility, same as OpenVPN)
    try:
        syslog = logging.handlers.SysLogHandler(
            address="/dev/log",
            facility=logging.handlers.SysLogHandler.LOG_DAEMON,
        )
        syslog.setLevel(logging.INFO)
        syslog.setFormatter(logging.Formatter("vpn-portal-openvpn: %(levelname)s %(message)s"))
        logger.addHandler(syslog)
    except Exception:
        pass  # syslog may not be available (containers, tests)

    # Stderr (captured by OpenVPN log)
    stderr = logging.StreamHandler(sys.stderr)
    stderr.setLevel(logging.DEBUG if os.environ.get("DEBUG") else logging.WARNING)
    stderr.setFormatter(logging.Formatter("%(levelname)s: %(message)s"))
    logger.addHandler(stderr)


# ---------------------------------------------------------------------------
# OAuth2 client credentials
# ---------------------------------------------------------------------------


def _load_cached_token() -> str | None:
    """Load a cached access token if still valid."""
    cache_path = Path(TOKEN_CACHE_PATH)
    if not cache_path.exists():
        return None

    try:
        data = json.loads(cache_path.read_text())
        expires_at = data.get("expires_at", 0)
        if time.time() < (expires_at - TOKEN_EXPIRY_MARGIN):
            logger.debug("Using cached token (expires_at=%s)", expires_at)
            return data["access_token"]
        logger.debug("Cached token expired")
    except (json.JSONDecodeError, KeyError, OSError) as exc:
        logger.warning("Failed to read token cache: %s", exc)

    return None


def _save_cached_token(access_token: str, expires_in: int) -> None:
    """Save access token to cache file with restricted permissions."""
    cache_path = Path(TOKEN_CACHE_PATH)
    try:
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        data = {"access_token": access_token, "expires_at": time.time() + expires_in}
        cache_path.write_text(json.dumps(data))
        cache_path.chmod(0o600)
        logger.debug("Token cached (expires_in=%ds)", expires_in)
    except OSError as exc:
        logger.warning("Failed to write token cache: %s", exc)


def get_access_token(client: httpx.Client) -> str:
    """Obtain an access token via OAuth2 client_credentials grant.

    Uses file-based caching to avoid requesting a new token on every call.

    Returns:
        Access token string.

    Raises:
        SystemExit: If token acquisition fails.
    """
    cached = _load_cached_token()
    if cached:
        return cached

    if not all([CLIENT_ID, CLIENT_SECRET, TOKEN_URL]):
        logger.error(
            "OAuth2 not configured. Set OPENVPN_OAUTH2_CLIENT_ID, "
            "OPENVPN_OAUTH2_CLIENT_SECRET, and OPENVPN_OAUTH2_TOKEN_URL"
        )
        sys.exit(1)

    try:
        response = client.post(
            TOKEN_URL,
            data={
                "grant_type": "client_credentials",
                "client_id": CLIENT_ID,
                "client_secret": CLIENT_SECRET,
                "scope": OAUTH2_SCOPE,
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        response.raise_for_status()
    except httpx.HTTPError as exc:
        logger.error("OAuth2 token request failed: %s", exc)
        sys.exit(1)

    token_data = response.json()
    access_token = token_data["access_token"]
    expires_in = token_data.get("expires_in", 300)

    _save_cached_token(access_token, expires_in)
    return access_token


# ---------------------------------------------------------------------------
# API helpers
# ---------------------------------------------------------------------------


def _api_request(
    client: httpx.Client,
    path: str,
    token: str,
    payload: dict,
) -> httpx.Response:
    """Make an authenticated POST request to the VPN Portal internal API."""
    url = f"{API_BASE_URL.rstrip('/')}{path}"
    return client.post(
        url,
        json=payload,
        headers={"Authorization": f"Bearer {token}"},
        timeout=10.0,
    )


def _cidr_to_netmask(prefix: int) -> str:
    """Convert CIDR prefix length to dotted-decimal netmask."""
    bits = (0xFFFFFFFF << (32 - prefix)) & 0xFFFFFFFF
    return f"{(bits >> 24) & 0xFF}.{(bits >> 16) & 0xFF}.{(bits >> 8) & 0xFF}.{bits & 0xFF}"


def _write_routes(config_file: str, routes: list[str]) -> None:
    """Write push-route directives to the OpenVPN temporary config file."""
    try:
        with open(config_file, "w") as fh:
            for route in routes:
                parts = route.split("/")
                if len(parts) == 2:
                    network = parts[0]
                    netmask = _cidr_to_netmask(int(parts[1]))
                    fh.write(f'push "route {network} {netmask}"\n')
        logger.info("Wrote %d routes to %s", len(routes), config_file)
    except OSError as exc:
        logger.error("Failed to write routes to %s: %s", config_file, exc)


def _get_config_file_path() -> str | None:
    """Extract the OpenVPN temporary config file path from sys.argv.

    OpenVPN appends the path as the last positional argument after the
    script's own flags (e.g. /tmp/openvpn_cc_XXXXXX).
    """
    for arg in reversed(sys.argv):
        if not arg.startswith("-") and arg != sys.argv[0]:
            return arg
    return None


# ---------------------------------------------------------------------------
# OpenVPN management interface
# ---------------------------------------------------------------------------


def _management_send(sock: socket.socket, command: str) -> str:
    """Send a command to the OpenVPN management interface and return response."""
    sock.sendall(f"{command}\n".encode())
    chunks = []
    while True:
        chunk = sock.recv(4096)
        if not chunk:
            break
        chunks.append(chunk)
        decoded = b"".join(chunks).decode()
        if any(marker in decoded for marker in ("SUCCESS:", "ERROR:", "\r\nEND\r\n")):
            break
    return b"".join(chunks).decode().strip()


def _kill_client_via_management(client_addr: str) -> None:
    """Kill a client via the OpenVPN management interface using their real address.

    Uses ``kill <ip:port>`` which works even after tls-verify rejects a
    certificate during renegotiation.  ``kill <common_name>`` does NOT work
    in this case because OpenVPN removes the client from its CN-indexed list
    after TLS failure, but the data channel stays alive.

    OpenVPN is single-threaded: it blocks while running the tls-verify script.
    Connecting to the management socket from within the script causes a deadlock.

    This function forks a background process that waits for the script to exit
    (and OpenVPN to resume), then sends ``kill <ip:port>``.
    """
    if not client_addr:
        logger.warning("No client address to kill")
        return

    try:
        pid = os.fork()
    except OSError as exc:
        logger.warning("Failed to fork kill process for %s: %s", client_addr, exc)
        return

    if pid > 0:
        logger.info("Forked management kill process (pid=%d) for %s", pid, client_addr)
        return

    # Child — detach, wait for OpenVPN to resume, then kill.
    # After setsid() the original stderr pipe is closed, so we use the
    # syslog module directly (DGRAM socket to /dev/log always works).
    import syslog as _syslog

    try:
        os.setsid()
        time.sleep(2)
        with socket.create_connection((MANAGEMENT_HOST, MANAGEMENT_PORT), timeout=5) as sock:
            sock.recv(4096)  # welcome banner

            response = _management_send(sock, f"kill {client_addr}")
            _syslog.syslog(
                _syslog.LOG_INFO,
                f"vpn-portal-openvpn: kill {client_addr}: {response}",
            )

            sock.sendall(b"quit\n")
    except Exception as exc:
        _syslog.syslog(
            _syslog.LOG_WARNING,
            f"vpn-portal-openvpn: management kill {client_addr} failed: {exc}",
        )
    finally:
        os._exit(0)


# ---------------------------------------------------------------------------
# Handlers
# ---------------------------------------------------------------------------


def handle_connect(client: httpx.Client, token: str) -> int:
    """Handle OpenVPN client-connect event.

    1. Validate the certificate via POST /api/v1/internal/validate
    2. Write routes to the temp config file
    3. Record the connection via POST /api/v1/internal/connect

    Returns:
        Exit code (0 = allow, 1 = deny).
    """
    common_name = os.environ.get("common_name", "")  # noqa: SIM112 - OpenVPN sets lowercase names
    client_ip = os.environ.get("untrusted_ip", "")  # noqa: SIM112 - OpenVPN sets lowercase names
    assigned_ip = os.environ.get("ifconfig_pool_remote_ip", "")  # noqa: SIM112 - OpenVPN sets lowercase names

    if not common_name:
        logger.error("Missing common_name environment variable")
        return 1

    logger.info("client-connect: CN=%s IP=%s VPN_IP=%s", common_name, client_ip, assigned_ip)

    # 1. Validate certificate
    resp = _api_request(
        client,
        "/api/v1/internal/validate",
        token,
        {
            "common_name": common_name,
            "client_ip": client_ip,
            "assigned_ip": assigned_ip,
        },
    )

    if resp.status_code != 200:
        logger.error("Validate API returned %d: %s", resp.status_code, resp.text)
        return 1

    data = resp.json()
    if not data.get("valid"):
        logger.warning("Certificate rejected: CN=%s reason=%s", common_name, data.get("reason"))
        return 1

    # 2. Write routes to temp config file
    routes = data.get("routes", [])
    config_file = _get_config_file_path()
    if config_file and routes:
        _write_routes(config_file, routes)

    # 3. Record connection (best-effort, don't deny on failure)
    resp = _api_request(
        client,
        "/api/v1/internal/connect",
        token,
        {
            "common_name": common_name,
            "client_ip": client_ip,
            "assigned_ip": assigned_ip,
        },
    )

    if resp.status_code != 200:
        logger.warning("Connect API returned %d: %s", resp.status_code, resp.text)

    return 0


def handle_reneg(client: httpx.Client, token: str) -> int:
    """Handle OpenVPN tls-verify event (called on TLS renegotiation).

    Re-validates the certificate via POST /api/v1/internal/validate.
    This ensures expired or revoked certificates are disconnected promptly
    when combined with reneg-sec in server.conf.

    OpenVPN calls tls-verify with two positional args: depth and subject.
    At depth > 0 (CA chain), we accept without checking.
    At depth 0 (client cert), we validate against the API.

    Returns:
        Exit code (0 = allow, 1 = deny / disconnect).
    """
    # tls-verify passes depth as first positional arg
    depth = 0
    for arg in sys.argv:
        if arg.isdigit():
            depth = int(arg)
            break

    # Only validate client certificate (depth 0), accept CA chain
    if depth > 0:
        return 0

    # At depth 0, common_name is available via X509_0_CN or common_name
    common_name = os.environ.get("common_name", "") or os.environ.get("X509_0_CN", "")  # noqa: SIM112 - OpenVPN sets lowercase names
    client_ip = os.environ.get("untrusted_ip", "")  # noqa: SIM112 - OpenVPN sets lowercase names
    client_port = os.environ.get("untrusted_port", "")  # noqa: SIM112 - OpenVPN sets lowercase names

    if not common_name:
        logger.error("tls-verify: missing common_name / X509_0_CN")
        return 1

    logger.info("tls-verify: CN=%s IP=%s:%s depth=%d", common_name, client_ip, client_port, depth)

    # Build address for management kill (ip:port)
    client_addr = f"{client_ip}:{client_port}" if client_port else client_ip

    try:
        resp = _api_request(
            client,
            "/api/v1/internal/validate",
            token,
            {
                "common_name": common_name,
                "client_ip": client_ip,
            },
        )
    except Exception as exc:
        # On API failure, allow the connection to stay (fail-open for reneg)
        logger.warning("tls-verify: API request failed: %s (allowing)", exc)
        return 0

    if resp.status_code != 200:
        logger.error("tls-verify: Validate API returned %d: %s", resp.status_code, resp.text)
        _kill_client_via_management(client_addr)
        return 1

    data = resp.json()
    if not data.get("valid"):
        logger.warning(
            "tls-verify: Certificate rejected: CN=%s reason=%s", common_name, data.get("reason")
        )
        _kill_client_via_management(client_addr)
        return 1

    return 0


def handle_disconnect(client: httpx.Client, token: str) -> int:
    """Handle OpenVPN client-disconnect event.

    Records the disconnection via POST /api/v1/internal/disconnect.

    Returns:
        Exit code (0 = success). OpenVPN ignores the exit code for disconnect.
    """
    common_name = os.environ.get("common_name", "")  # noqa: SIM112 - OpenVPN sets lowercase names
    bytes_received = int(os.environ.get("bytes_received", "0"))  # noqa: SIM112 - OpenVPN sets lowercase names
    bytes_sent = int(os.environ.get("bytes_sent", "0"))  # noqa: SIM112 - OpenVPN sets lowercase names

    if not common_name:
        logger.error("Missing common_name environment variable")
        return 1

    logger.info("client-disconnect: CN=%s rx=%d tx=%d", common_name, bytes_received, bytes_sent)

    resp = _api_request(
        client,
        "/api/v1/internal/disconnect",
        token,
        {
            "common_name": common_name,
            "bytes_received": bytes_received,
            "bytes_sent": bytes_sent,
        },
    )

    if resp.status_code != 200:
        logger.error("Disconnect API returned %d: %s", resp.status_code, resp.text)
        return 1

    return 0


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> int:
    """Entry point for the OpenVPN hook script."""
    setup_logging()

    parser = argparse.ArgumentParser(
        description="OpenVPN client-connect/disconnect hook for VPN Portal",
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--connect", action="store_true", help="Handle client-connect event")
    group.add_argument("--disconnect", action="store_true", help="Handle client-disconnect event")
    group.add_argument(
        "--reneg", action="store_true", help="Handle tls-verify event (renegotiation)"
    )

    # parse_known_args because OpenVPN appends extra positional args
    args, _unknown = parser.parse_known_args()

    with httpx.Client(timeout=10.0) as http_client:
        token = get_access_token(http_client)

        if args.connect:
            return handle_connect(http_client, token)
        if args.disconnect:
            return handle_disconnect(http_client, token)
        return handle_reneg(http_client, token)


if __name__ == "__main__":
    sys.exit(main())
