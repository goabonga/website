# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Support for the ``@browser`` scenarios: serve the application, build the web client.

The application of a scenario is served on a real socket with the settings the scenario
gave, and the web client is built once per run, from the sources of ``apps/frontend/web``,
the way ``npm run build`` does it in a deployment.
"""

import shutil
import subprocess
import tempfile
from pathlib import Path
from urllib.parse import urlparse

from e2e_support.server import LiveServer
from frontend.config import Settings
from frontend.main import create_app

APP_DIR = Path(__file__).resolve().parents[1]
WEB_DIR = APP_DIR / "web"

#: Seconds an npm command may take (``npm ci`` downloads the packages the first time).
NPM_TIMEOUT = 300

_build_root: Path | None = None
_build_error: str | None = None


class ClientBuildUnavailable(Exception):
    """The web client cannot be built here, with the reason."""


def _npm(*args: str, cwd: Path) -> None:
    result = subprocess.run(
        ["npm", *args],
        cwd=cwd,
        capture_output=True,
        text=True,
        timeout=NPM_TIMEOUT,
        check=False,
    )
    if result.returncode != 0:
        raise ClientBuildUnavailable(
            f"npm {' '.join(args)} failed: {(result.stderr or result.stdout).strip()[-300:]}"
        )


def client_build() -> Path:
    """The directory holding the build of the web client (built on first use).

    The sources are copied to a temporary directory, so that the working tree gets
    neither ``node_modules`` nor ``dist`` nor a regenerated template.
    Raises :class:`ClientBuildUnavailable` when node or the npm registry is not available.
    """
    global _build_root, _build_error
    if _build_error is not None:
        raise ClientBuildUnavailable(_build_error)
    if _build_root is not None:
        return _build_root / "web" / "dist"
    if shutil.which("node") is None or shutil.which("npm") is None:
        _build_error = "node and npm are required to build the web client"
        raise ClientBuildUnavailable(_build_error)
    root = Path(tempfile.mkdtemp(prefix="frontend-build-"))
    try:
        shutil.copytree(
            WEB_DIR, root / "web", ignore=shutil.ignore_patterns("node_modules", "dist")
        )
        _npm("ci", "--no-audit", "--no-fund", cwd=root / "web")
        _npm("run", "build", cwd=root / "web")
    except (ClientBuildUnavailable, subprocess.TimeoutExpired, OSError) as exc:
        shutil.rmtree(root, ignore_errors=True)
        _build_error = str(exc)
        raise ClientBuildUnavailable(_build_error) from exc
    _build_root = root
    return root / "web" / "dist"


def remove_client_build() -> None:
    global _build_root
    if _build_root is not None:
        shutil.rmtree(_build_root, ignore_errors=True)
        _build_root = None


def serve(context) -> str:
    """Serve an application built from the scenario settings; return its URL."""
    settings = Settings(_env_file=None, **context.overrides)
    server = LiveServer(create_app(settings)).start()
    context.servers.append(server)
    return server.url


def stop_servers(context) -> None:
    """Stop what the scenario started, the last one first: the application delivers its pending
    analytics events when it stops, so it must stop before the collector that receives them."""
    servers, context.servers = getattr(context, "servers", []), []
    for server in reversed(servers):
        server.stop()


#: Hosts of the servers started by the scenarios.
LOOPBACK = ("127.0.0.1", "localhost")


def keep_to_the_stack(context, scenario) -> None:
    """Let a browser scenario reach what it serves and nothing else.

    The page asks Google Fonts for a font: that request is answered with an empty style sheet,
    so that a scenario needs no network. Any other request to a third party fails, which the
    scenario reports as a browser error. Requests to the servers of the scenario are not
    intercepted. A scenario tagged ``@cross-origin`` is not guarded at all: with a route
    installed, Playwright does not let the browser complete the CORS preflight of the
    credentialed requests the web client sends to the analytics service.
    """
    tags = scenario.effective_tags
    if "browser" not in tags or "cross-origin" in tags or getattr(context, "page", None) is None:
        return

    def handle(route):
        if route.request.url.startswith("https://fonts.googleapis.com/"):
            route.fulfill(status=200, content_type="text/css", body="")
        else:
            route.abort()

    context.browser_context.route(lambda url: urlparse(url).hostname not in LOOPBACK, handle)
