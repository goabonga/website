# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Helpers asserting the admin sidebar on pages rendered by the real application.

Unlike the route tests, nothing is mocked at the template level: requests go
through the ASGI application, the Jinja templates are rendered for real, the
database is a throw-away SQLite file and every outbound service client is
replaced by a mock.

Authentication mimics production: the access token only carries OIDC scopes
and the RBAC scopes come from the token exchange, which grants the requested
scopes the user holds (wildcards included).
"""

import logging
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import AsyncExitStack, asynccontextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from html.parser import HTMLParser
from unittest.mock import AsyncMock, PropertyMock, patch

import httpx
from internal.auth.models import User
from internal.services.token_exchange import TokenExchangeClient, TokenExchangeError


def _import_app():
    """Import the application without keeping the logging setup its import performs."""
    root = logging.getLogger()
    handlers, level = list(root.handlers), root.level
    try:
        from internal.main import app
    finally:
        root.handlers[:] = handlers
        root.setLevel(level)
    return app


app = _import_app()

USER_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")
USER_EMAIL = "admin@test.local"
USER_NAME = "Test Admin"


@dataclass(frozen=True)
class Section:
    """A sidebar link.

    ``access`` is the scope opening the pages of the section; ``gate`` the scope revealing the
    link (None: always shown).
    """

    href: str
    access: str
    gate: str | None = None


# Sidebar sections, keyed by the ``active_section`` the pages pass to the template.
SECTIONS: dict[str, Section] = {
    "analytics": Section("/analytics", "analytics:*"),
}

# Targets of the outbound service clients replaced by mocks.
CLIENTS: tuple[str, ...] = ("internal.routes.analytics.analytics_client",)


@dataclass(frozen=True)
class Page:
    """A page rendering the sidebar: its URL and the section it belongs to."""

    path: str
    section: str
    prepare: Callable[..., Awaitable[dict]] | None = None


def visible_hrefs(scopes: list[str]) -> set[str]:
    """Return the links the sidebar must show to a user holding ``scopes``."""
    user = User(id=USER_ID, scopes=scopes)
    return {
        section.href
        for section in SECTIONS.values()
        if section.gate is None or user.has_scope(section.gate)
    }


class _SidebarParser(HTMLParser):
    """Collect the links of the ``admin-nav`` list and the user block."""

    def __init__(self) -> None:
        super().__init__()
        self.links: list[tuple[str, bool]] = []
        self.user_email: str | None = None
        self._in_nav = False
        self._in_email = False

    def handle_starttag(self, tag, attrs):
        attributes = dict(attrs)
        classes = (attributes.get("class") or "").split()
        if tag == "ul" and "admin-nav" in classes:
            self._in_nav = True
        elif tag == "a" and self._in_nav:
            self.links.append((attributes.get("href") or "", "active" in classes))
        elif tag == "div" and "user-email" in classes:
            self._in_email = True

    def handle_endtag(self, tag):
        if tag == "ul":
            self._in_nav = False
        elif tag == "div":
            self._in_email = False

    def handle_data(self, data):
        if self._in_email and data.strip():
            self.user_email = data.strip()


def parse_sidebar(html: str) -> _SidebarParser:
    """Parse the sidebar of a rendered page."""
    parser = _SidebarParser()
    parser.feed(html)
    return parser


def assert_sidebar(html: str, scopes: list[str], section: str, *, strict: bool = False) -> None:
    """Assert the sidebar shows the links ``scopes`` permit, with ``section`` active.

    Only the sections registered in ``SECTIONS`` are checked, so that the tests of a feature
    keep passing when later features add their own link; ``strict`` also rejects unknown links.
    """
    sidebar = parse_sidebar(html)
    hrefs = [href for href, _ in sidebar.links]
    assert len(hrefs) == len(set(hrefs)), f"Duplicate sidebar links: {hrefs}"
    known = {candidate.href for candidate in SECTIONS.values()}
    shown = set(hrefs) if strict else set(hrefs) & known
    assert shown == visible_hrefs(scopes), (
        f"Sidebar links {sorted(shown)} do not match scopes {scopes}: "
        f"expected {sorted(visible_hrefs(scopes))}"
    )
    active = [href for href, is_active in sidebar.links if is_active]
    assert active == [SECTIONS[section].href], (
        f"Expected the only active link to be {SECTIONS[section].href!r}, got {active}"
    )
    assert sidebar.user_email == USER_EMAIL, f"Unexpected sidebar user {sidebar.user_email!r}"


class Env:
    """The running application: SQLite database, mocked clients and fake token exchange."""

    def __init__(
        self,
        stack: AsyncExitStack,
        session_maker,
        clients: dict[str, AsyncMock],
    ) -> None:
        self.stack = stack
        self.session_maker = session_maker
        self.clients = clients
        self.rbac_scopes: list[str] = []

    def client(self, name: str) -> AsyncMock:
        """Return the mock replacing the service client ``name`` (e.g. ``billing.billing_client``)."""
        return self.clients[name]

    def patch(self, target: str, new) -> None:
        """Patch ``target`` until the application stops."""
        self.stack.enter_context(patch(target, new))

    async def add(self, *rows) -> None:
        """Insert ORM rows into the database."""
        async with self.session_maker() as session:
            session.add_all(rows)
            await session.commit()
            for row in rows:
                await session.refresh(row)

    async def get(self, path: str, scopes: list[str]) -> httpx.Response:
        """GET ``path`` as a user whose RBAC scopes are ``scopes``."""
        self.rbac_scopes = scopes
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://test",
            cookies={"access_token": "test-token"},
            follow_redirects=False,
        ) as http:
            return await http.get(path)


CAMPAIGN_ID = "11111111-1111-1111-1111-111111111111"
IP_ADDRESS = "192.168.1.1"


async def configure_analytics(env: "Env") -> dict:
    """Make the analytics service return one campaign, one IP and an overview."""
    analytics = env.client("analytics.analytics_client")
    day = datetime(2024, 1, 15, tzinfo=UTC)
    analytics.get_overview.return_value = {
        "total_sessions": 100,
        "unique_visitors": 80,
        "total_pageviews": 500,
        "total_events": 50,
    }
    for method in (
        "get_daily_stats",
        "get_country_stats",
        "get_device_stats",
        "get_browser_stats",
        "get_referrer_stats",
        "get_page_stats",
        "get_event_stats",
        "get_campaign_pixels",
    ):
        getattr(analytics, method).return_value = []
    analytics.get_campaigns.return_value = [
        {
            "id": CAMPAIGN_ID,
            "name": "Spring",
            "tracking_key": "spring",
            "is_active": True,
            "click_count": 42,
            "unique_click_count": 30,
            "pixel_count": 5,
            "total_opens": 1000,
            "created_at": day,
        }
    ]
    analytics.get_campaign_detail.return_value = {
        **analytics.get_campaigns.return_value[0],
        "description": "Spring campaign",
        "updated_at": day,
        "destination_url": "https://example.com",
        "clicks_by_day": [],
        "clicks_by_country": [],
    }
    analytics.get_ip_stats.return_value = [
        {
            "ip_address": IP_ADDRESS,
            "sessions": 50,
            "pageviews": 120,
            "countries": ["US"],
            "first_seen": day,
            "last_seen": day,
        }
    ]
    analytics.get_ip_detail.return_value = {
        **analytics.get_ip_stats.return_value[0],
        "total_sessions": 50,
        "total_pageviews": 120,
        "total_events": 30,
        "cities": ["New York"],
        "browsers": ["Chrome"],
        "device_types": ["Desktop"],
        "operating_systems": ["Windows"],
        "referrers": ["https://google.com"],
        "pages": [{"page_url": "/home", "pageviews": 50}],
        "events": [],
        "sessions_by_day": [],
    }
    return {}


# Pages rendering the sidebar, grouped by the feature that introduced them.
PAGES: dict[str, list[Page]] = {
    "analytics": [
        Page("/analytics", "analytics", configure_analytics),
        Page("/analytics/campaigns", "analytics", configure_analytics),
        Page(f"/analytics/campaigns/{CAMPAIGN_ID}", "analytics", configure_analytics),
        Page("/analytics/ips", "analytics", configure_analytics),
        Page(f"/analytics/ips/{IP_ADDRESS}", "analytics", configure_analytics),
    ],
}


async def prepare_page(env: Env, page: Page) -> str:
    """Prepare the data ``page`` needs and return its concrete URL path."""
    params = await page.prepare(env) if page.prepare else {}
    return page.path.format(**params)


def scope_sets(section: str) -> list[list[str]]:
    """Return the scope combinations to try on the pages of ``section``.

    Each one opens the pages of the section; the others add the scopes revealing
    sidebar links, one by one and all together, and finally a super administrator.
    """
    access = SECTIONS[section].access
    gates = list(dict.fromkeys(s.gate for s in SECTIONS.values() if s.gate))
    candidates = [[access], *[[access, gate] for gate in gates], [access, *gates], ["*"]]
    unique = []
    for scopes in candidates:
        scopes = list(dict.fromkeys(scopes))
        if scopes not in unique:
            unique.append(scopes)
    return unique


def sidebar_hrefs(html: str) -> list[str]:
    """Return the links of the sidebar of a rendered page."""
    return [href for href, _ in parse_sidebar(html).links]


@asynccontextmanager
async def running_app(tmp_path) -> AsyncIterator[Env]:
    """Run the application against SQLite with mocked clients and token exchange."""
    async with AsyncExitStack() as stack:
        session_maker = None

        clients = {}
        for target in CLIENTS:
            mock = AsyncMock()
            stack.enter_context(patch(target, new=mock))
            clients[target.removeprefix("internal.routes.")] = mock

        env = Env(stack, session_maker, clients)
        claims = {
            "sub": str(USER_ID),
            "email": USER_EMAIL,
            "name": USER_NAME,
            "scope": "openid profile email",
        }

        async def exchange(token, requested):
            rbac = User(id=USER_ID, scopes=env.rbac_scopes)
            granted = [scope for scope in requested if rbac.has_scope(scope)]
            if not granted:
                raise TokenExchangeError("insufficient_scope", error_code="insufficient_scope")
            return {"scope": " ".join(granted), "access_token": "exchanged-test-token"}

        stack.enter_context(patch("internal.auth.dependencies.settings.oauth2_issuer", "https://x"))
        stack.enter_context(
            patch(
                "internal.auth.jwt.jwt_validator.validate_token_with_introspection",
                new=AsyncMock(return_value=claims),
            )
        )
        stack.enter_context(
            patch.object(TokenExchangeClient, "is_configured", new_callable=PropertyMock)
        ).return_value = True
        stack.enter_context(
            patch(
                "internal.services.token_exchange.token_exchange_client.validate_token_scopes",
                new=exchange,
            )
        )
        yield env
