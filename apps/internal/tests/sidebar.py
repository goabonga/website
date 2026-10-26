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
from contextlib import AsyncExitStack, asynccontextmanager, contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from html.parser import HTMLParser
from types import SimpleNamespace
from unittest.mock import AsyncMock, PropertyMock, patch

import httpx
from internal.auth.models import User
from internal.database import Base, get_db
from internal.models.conversation import Conversation, Message
from internal.models.knowledge import KnowledgeEntry, KnowledgeNamespace
from internal.models.prompt import SystemPrompt, SystemPromptVersion
from internal.services.token_exchange import TokenExchangeClient, TokenExchangeError
from internal.services.vpn_portal_client import VPNSession, VPNSessionsResponse
from sqlalchemy import JSON, Uuid
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine


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
    "dashboard": Section("/", "conversations:*"),
    "conversations": Section("/conversations", "conversations:*"),
    "knowledge": Section("/knowledge", "knowledge:*"),
    "namespaces": Section("/namespaces", "namespaces:*"),
    "prompts": Section("/prompts", "prompts:*"),
    "analytics": Section("/analytics", "analytics:*"),
    "email_templates": Section("/email-templates", "email_templates:*"),
    "email_campaigns": Section("/email-campaigns", "email_campaigns:*"),
    "mailler": Section("/mailler", "mailler:*"),
    "contacts": Section("/contacts", "contacts:*"),
    "contact_groups": Section("/contact-groups", "contacts:*"),
    "vpn": Section("/vpn/sessions", "vpn:admin", "vpn:admin"),
    "billing": Section("/billing", "billing:*", "billing:read"),
    "team": Section("/team", "team:*"),
}

# Targets of the outbound service clients replaced by mocks.
CLIENTS: tuple[str, ...] = (
    "internal.routes.analytics.analytics_client",
    "internal.routes.admin.analytics_client",
    "internal.routes.admin.auth_client",
    "internal.routes.billing.billing_client",
    "internal.routes.vpn.vpn_portal_client",
    "internal.routes.team.team_client",
    "internal.routes.mailler.mailler_client",
    "internal.routes.contacts.mailler_client",
    "internal.routes.contact_groups.mailler_client",
    "internal.routes.email_templates.mailler_client",
    "internal.routes.email_campaigns.mailler_client",
)


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


@contextmanager
def _sqlite_column_types():
    """Map the PostgreSQL-only column types to portable ones, then restore them."""
    saved = []
    for table in Base.metadata.tables.values():
        for column in table.columns:
            saved.append((column, column.type))
            if isinstance(column.type, ARRAY | JSONB) or type(column.type).__name__ == "Vector":
                column.type = JSON()
            elif isinstance(column.type, Uuid) and type(column.type) is not Uuid:
                column.type = Uuid(as_uuid=True)
    try:
        yield
    finally:
        for column, column_type in saved:
            column.type = column_type


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
        return await self.request("GET", path, scopes)

    async def post(self, path: str, scopes: list[str], data: dict | None = None) -> httpx.Response:
        """POST the form ``data`` to ``path`` as a user whose RBAC scopes are ``scopes``."""
        return await self.request("POST", path, scopes, data=data)

    async def request(
        self, method: str, path: str, scopes: list[str], data: dict | None = None
    ) -> httpx.Response:
        """Send a request as a user whose RBAC scopes are ``scopes``, without following redirects."""
        self.rbac_scopes = scopes
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://test",
            cookies={"access_token": "test-token"},
            follow_redirects=False,
        ) as http:
            return await http.request(method, path, data=data)


async def seed_conversation(env: "Env") -> dict:
    """Create a conversation with two messages and a known owner."""
    conversation = Conversation(id=uuid.uuid4(), user_id=USER_ID, title="Hello")
    await env.add(conversation)
    await env.add(
        Message(id=uuid.uuid4(), conversation_id=conversation.id, role="user", content="Hi"),
        Message(id=uuid.uuid4(), conversation_id=conversation.id, role="assistant", content="Yo"),
    )
    env.client("admin.auth_client").get_user.return_value = {
        "id": str(USER_ID),
        "email": "owner@test.local",
        "name": "Owner",
    }
    return {"conversation": conversation.id}


async def seed_namespace(env: "Env") -> dict:
    """Create a knowledge namespace."""
    namespace = KnowledgeNamespace(slug="docs", name="Docs", is_public=True)
    await env.add(namespace)
    return {"namespace": namespace.id}


async def enable_openai(env: "Env") -> dict:
    """Pretend an OpenAI API key is configured."""
    env.patch("internal.config.settings.openai_api_key", "sk-test")
    return {}


async def seed_prompt(env: "Env") -> dict:
    """Create a prompt with a current version."""
    prompt = SystemPrompt(slug="support", name="Support", description="Support prompt")
    await env.add(prompt)
    await env.add(
        SystemPromptVersion(
            prompt_id=prompt.id, version=1, content="Be helpful.", metadata_={}, is_current=True
        )
    )
    return {"prompt": prompt.id}


async def seed_entry(env: "Env") -> dict:
    """Create a knowledge entry."""
    entry = KnowledgeEntry(question="Why?", answer="Because.", metadata_={})
    await env.add(entry)
    return {"entry": entry.id}


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


async def configure_vpn(env: "Env") -> dict:
    """Make the VPN portal return one session."""
    now = datetime.now(UTC)
    session = VPNSession(
        id="session-001",
        user_id="user-001",
        username="testuser",
        device_name="laptop",
        connected_at=now - timedelta(hours=2),
        assigned_ip="10.8.0.2",
        certificate_serial="ABC123DEF456",
        expires_at=now + timedelta(hours=22),
        scopes=["vpn:connect"],
        routes=["10.8.0.0/24"],
    )
    env.client("vpn.vpn_portal_client").get_sessions.return_value = VPNSessionsResponse(
        sessions=[session], total=1, page=1, per_page=20
    )
    return {}


async def configure_billing(env: "Env") -> dict:
    """Make the billing service return one SaaS app, product, price, customer and subscription."""
    created = datetime(2024, 1, 1)
    price = SimpleNamespace(
        id="price-1",
        stripe_price_id="stripe_price_1",
        unit_amount=1999,
        currency="eur",
        billing_type="recurring",
        recurring_interval="month",
        recurring_interval_count=1,
        usage_type="licensed",
        nickname="Monthly",
        is_active=True,
        created_at=created,
    )
    product = SimpleNamespace(
        id="prod-1",
        name="Pro",
        slug="pro",
        description="Pro plan",
        stripe_product_id="stripe_prod_1",
        is_active=True,
        sort_order=0,
        default_trial_days=0,
        is_recommended=False,
        features=[],
        limits={},
        metadata={},
        created_at=created,
        extra_data=SimpleNamespace(
            slug="pro",
            is_recommended=False,
            sort_order=0,
            default_trial_days=0,
            features=[{"label": "Feature 1", "highlight": False, "disabled": False}],
            limits={"max_users": 10},
        ),
    )
    customer = SimpleNamespace(
        id="cust-1",
        email="customer@example.com",
        name="Customer",
        stripe_customer_id="stripe_cus_1",
        external_id="ext-1",
        created_at=created,
    )
    subscription = SimpleNamespace(
        id="sub-1",
        customer_id="cust-1",
        stripe_subscription_id="stripe_sub_1",
        stripe_subscription_item_id="stripe_si_1",
        status="active",
        current_period_start=created,
        current_period_end=datetime(2024, 2, 1),
        cancel_at_period_end=False,
        canceled_at=None,
        created_at=created,
    )
    saas = SimpleNamespace(
        id="saas-1",
        name="Acme",
        slug="acme",
        description="Acme app",
        is_active=True,
        webhook_url="",
        webhook_secret="",
        branding=None,
        checkout_url_allowlist=["https://app.example.test"],
        stripe_connected=False,
        created_at=created,
        products=[],
    )
    billing = env.client("billing.billing_client")
    billing.list_saas_apps.return_value = [saas]
    billing.list_saas_clients.return_value = [
        SimpleNamespace(client_id="client-a", saas_app_id="saas-1", created_at=created)
    ]
    billing.get_saas_app.return_value = saas
    billing.list_products.return_value = [product]
    billing.get_product.return_value = product
    billing.list_prices.return_value = [price]
    billing.list_customers.return_value = [customer]
    billing.get_customer.return_value = customer
    billing.list_customer_subscriptions.return_value = [subscription]
    billing.list_subscriptions.return_value = [subscription]
    billing.get_subscription.return_value = subscription
    return {}


async def configure_team(env: "Env") -> dict:
    """Make the team service return one team, agent, workflow, conversation and memory entry."""
    created = datetime(2024, 1, 1)
    team = SimpleNamespace(
        id="team-1",
        name="Support",
        slug="support",
        description="Support team",
        is_active=True,
        config={},
        created_at=created,
        updated_at=created,
    )
    agent = SimpleNamespace(
        id="agent-1",
        team_id="team-1",
        name="Helper",
        role="assistant",
        description="Helps",
        system_prompt="You are helpful.",
        model="gpt-4o",
        provider="openai",
        is_active=True,
        config={},
        created_at=created,
    )
    workflow = SimpleNamespace(
        id="wf-1",
        team_id="team-1",
        name="Triage",
        description="Triage tickets",
        steps={},
        status="draft",
        config={},
        created_at=created,
    )
    conversation = SimpleNamespace(
        id="conv-1",
        slug="chat",
        title="Chat",
        type="general",
        status="active",
        extra={},
        created_at=created,
        updated_at=created,
    )
    message = SimpleNamespace(
        id="msg-1",
        conversation_id="conv-1",
        agent_id="agent-1",
        type="message",
        content={},
        text="Hello",
        visibility="public",
        created_at=created,
    )
    memory = SimpleNamespace(
        id="mem-1",
        team_id="team-1",
        agent_id=None,
        conversation_id=None,
        content="Fact",
        extra={},
        created_at=created,
    )
    skill = SimpleNamespace(
        id="skill-1",
        agent_id="agent-1",
        name="Search",
        description="Searches",
        config={},
        is_active=True,
        created_at=created,
    )
    client = env.client("team.team_client")
    client.list_teams.return_value = [team]
    client.get_team.return_value = team
    client.list_agents.return_value = [agent]
    client.get_agent.return_value = agent
    client.list_workflows.return_value = [workflow]
    client.list_conversations.return_value = [conversation]
    client.get_conversation.return_value = conversation
    client.list_messages.return_value = [message]
    client.list_memory.return_value = [memory]
    client.list_skills.return_value = [skill]
    client.get_skill.return_value = skill
    client.list_tools.return_value = []
    return {}


EMAIL_ID = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"


async def configure_mailler(env: "Env") -> dict:
    """Make the mailler service return statistics and one email."""
    mailler = env.client("mailler.mailler_client")
    counters = {"sent": 100, "delivered": 95, "bounced": 3, "failed": 2}
    mailler.get_stats.return_value = {
        "total": counters,
        "by_date": [{"date": "2024-01-15", **counters}],
        "by_provider": {"ses": counters},
    }
    mailler.get_providers.return_value = ["ses", "smtp"]
    email = {
        "id": EMAIL_ID,
        "to_email": "user@example.com",
        "to_name": "User",
        "from_email": "noreply@example.com",
        "from_name": "Example",
        "reply_to": "support@example.com",
        "subject": "Test Email",
        "status": "delivered",
        "provider": "ses",
        "provider_message_id": "ses-msg-001",
        "retry_count": 0,
        "task_id": "task-1",
        "html_content": "<p>Hello</p>",
        "text_content": "Hello",
        "created_at": "2024-01-15T12:00:00Z",
        "scheduled_at": None,
        "queued_at": "2024-01-15T12:00:01Z",
        "sent_at": "2024-01-15T12:00:03Z",
        "delivered_at": "2024-01-15T12:00:05Z",
        "bounced_at": None,
        "failed_at": None,
        "error_message": None,
        "client_id": "client-001",
        "user_id": "user-001",
        "metadata": {"template": "welcome"},
    }
    mailler.get_emails.return_value = {
        "items": [email],
        "total": 1,
        "page": 1,
        "page_size": 20,
        "pages": 1,
    }
    mailler.get_email.return_value = email
    return {}


def _page(items: list[dict], page_size: int = 20) -> dict:
    """Build a paginated mailler API response."""
    return {"items": items, "total": len(items), "page": 1, "page_size": page_size, "pages": 1}


async def configure_contacts(env: "Env") -> dict:
    """Make the mailler service return one contact and one group."""
    contact = {
        "id": 42,
        "email": "test@example.com",
        "first_name": "Test",
        "last_name": "User",
        "status": "active",
        "source": "manual",
        "groups": [],
        "created_at": "2024-01-01T00:00:00Z",
        "updated_at": "2024-01-01T00:00:00Z",
    }
    group = {
        "id": 1,
        "name": "Newsletter",
        "slug": "newsletter",
        "description": "Newsletter subscribers",
        "member_count": 5,
        "is_dynamic": False,
        "created_at": "2024-01-01T00:00:00Z",
        "updated_at": "2024-01-01T00:00:00Z",
    }
    mailler = env.client("contacts.mailler_client")
    mailler.get_contacts.return_value = _page([contact], 50)
    mailler.get_contact.return_value = contact
    mailler.get_contact_groups.return_value = _page([group], 100)
    return {}


async def configure_contact_groups(env: "Env") -> dict:
    """Make the mailler service return one group with one member."""
    group = {
        "id": 1,
        "name": "Newsletter",
        "slug": "newsletter",
        "description": "Newsletter subscribers",
        "member_count": 1,
        "is_dynamic": False,
        "created_at": "2024-01-01T00:00:00Z",
        "updated_at": "2024-01-01T00:00:00Z",
    }
    contact = {
        "id": 1,
        "email": "test@example.com",
        "first_name": "Test",
        "last_name": "User",
        "full_name": "Test User",
        "status": "active",
        "source": "manual",
        "groups": [],
        "created_at": "2024-01-01T00:00:00Z",
        "updated_at": "2024-01-01T00:00:00Z",
    }
    mailler = env.client("contact_groups.mailler_client")
    mailler.get_contact_groups.return_value = _page([group])
    mailler.get_contact_group.return_value = group
    mailler.get_group_contacts.return_value = _page([contact], 50)
    mailler.get_contacts.return_value = _page([contact], 50)
    mailler.get_contacts_not_in_group.return_value = _page([contact], 50)
    return {}


async def configure_email_templates(env: "Env") -> dict:
    """Make the mailler service return one email template."""
    template = {
        "id": 1,
        "slug": "welcome-email",
        "name": "Welcome Email",
        "description": "A welcome email template",
        "subject_template": "Welcome %first_name%!",
        "mjml_source": "<mjml><mj-body></mj-body></mjml>",
        "html_compiled": "<html><body>Hello</body></html>",
        "plain_text": "Hello",
        "status": "active",
        "variables": ["first_name", "email"],
        "created_at": "2024-01-15T12:00:00Z",
        "updated_at": "2024-01-15T12:00:00Z",
    }
    mailler = env.client("email_templates.mailler_client")
    mailler.get_templates.return_value = {"items": [template], "total": 1, "pages": 1}
    mailler.get_template.return_value = template
    return {}


async def configure_email_campaigns(env: "Env") -> dict:
    """Make the mailler service return one draft campaign with its form data."""
    stats = {
        "total_recipients": 50,
        "sent_count": 0,
        "delivered_count": 0,
        "opened_count": 0,
        "clicked_count": 0,
        "bounced_count": 0,
        "complained_count": 0,
        "failed_count": 0,
        "progress_percent": 0,
        "open_rate": 0,
        "click_rate": 0,
        "bounce_rate": 0,
        "complaint_rate": 0,
    }
    campaign = {
        "id": 1,
        "name": "Newsletter January",
        "status": "draft",
        "template_id": 1,
        "group_id": 1,
        "total_recipients": 50,
        "sent_count": 0,
        "stats": stats,
        "created_at": "2024-01-15T12:00:00Z",
        "updated_at": "2024-01-15T12:00:00Z",
    }
    mailler = env.client("email_campaigns.mailler_client")
    mailler.get_campaigns.return_value = {"items": [campaign], "total": 1, "pages": 1}
    mailler.get_campaign.return_value = campaign
    mailler.get_campaign_sends.return_value = {"items": [], "total": 0}
    mailler.get_templates.return_value = {
        "items": [{"id": 1, "name": "Welcome", "slug": "welcome", "status": "active"}]
    }
    mailler.get_contact_groups.return_value = {
        "items": [{"id": 1, "name": "Subscribers", "slug": "subscribers"}]
    }
    mailler.get_providers.return_value = [{"name": "ses", "label": "Amazon SES"}]
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
    "dashboard": [
        Page("/", "dashboard"),
        Page("/conversations", "conversations"),
        Page("/conversations/{conversation}", "conversations", seed_conversation),
    ],
    "vpn": [
        Page("/vpn/sessions", "vpn", configure_vpn),
    ],
    "billing": [
        Page("/billing", "billing", configure_billing),
        Page("/billing/saas/new", "billing", configure_billing),
        Page("/billing/saas/saas-1", "billing", configure_billing),
        Page("/billing/saas/saas-1/edit", "billing", configure_billing),
        Page("/billing/saas/saas-1/products", "billing", configure_billing),
        Page("/billing/saas/saas-1/products/new", "billing", configure_billing),
        Page("/billing/saas/saas-1/products/prod-1", "billing", configure_billing),
        Page("/billing/saas/saas-1/products/prod-1/edit", "billing", configure_billing),
        Page("/billing/saas/saas-1/products/prod-1/prices/new", "billing", configure_billing),
        Page("/billing/saas/saas-1/customers", "billing", configure_billing),
        Page("/billing/saas/saas-1/customers/cust-1", "billing", configure_billing),
        Page("/billing/saas/saas-1/subscriptions", "billing", configure_billing),
        Page("/billing/saas/saas-1/subscriptions/sub-1", "billing", configure_billing),
    ],
    "team": [
        Page("/team", "team", configure_team),
        Page("/team/new", "team", configure_team),
        Page("/team/team-1", "team", configure_team),
        Page("/team/team-1/edit", "team", configure_team),
        Page("/team/team-1/agents", "team", configure_team),
        Page("/team/team-1/agents/new", "team", configure_team),
        Page("/team/team-1/agents/agent-1", "team", configure_team),
        Page("/team/team-1/agents/agent-1/edit", "team", configure_team),
        Page("/team/team-1/agents/agent-1/skills/skill-1/edit", "team", configure_team),
        Page("/team/team-1/workflows", "team", configure_team),
        Page("/team/team-1/workflows/new", "team", configure_team),
        Page("/team/team-1/workflows/wf-1/edit", "team", configure_team),
        Page("/team/team-1/run", "team", configure_team),
        Page("/team/team-1/conversations", "team", configure_team),
        Page("/team/team-1/conversations/conv-1", "team", configure_team),
        Page("/team/team-1/memory", "team", configure_team),
    ],
    "mailler": [
        Page("/mailler", "mailler", configure_mailler),
        Page("/mailler/emails", "mailler", configure_mailler),
        Page(f"/mailler/emails/{EMAIL_ID}", "mailler", configure_mailler),
    ],
    "contacts": [
        Page("/contacts", "contacts", configure_contacts),
        Page("/contacts/new", "contacts", configure_contacts),
        Page("/contacts/import", "contacts", configure_contacts),
        Page("/contacts/42", "contacts", configure_contacts),
        Page("/contacts/42/edit", "contacts", configure_contacts),
    ],
    "contact_groups": [
        Page("/contact-groups", "contact_groups", configure_contact_groups),
        Page("/contact-groups/new", "contact_groups", configure_contact_groups),
        Page("/contact-groups/1", "contact_groups", configure_contact_groups),
        Page("/contact-groups/1/edit", "contact_groups", configure_contact_groups),
        Page("/contact-groups/1/add-contacts", "contact_groups", configure_contact_groups),
    ],
    "email_templates": [
        Page("/email-templates", "email_templates", configure_email_templates),
        Page("/email-templates/new", "email_templates", configure_email_templates),
        Page("/email-templates/1", "email_templates", configure_email_templates),
        Page("/email-templates/1/edit", "email_templates", configure_email_templates),
    ],
    "email_campaigns": [
        Page("/email-campaigns", "email_campaigns", configure_email_campaigns),
        Page("/email-campaigns/new", "email_campaigns", configure_email_campaigns),
        Page("/email-campaigns/1", "email_campaigns", configure_email_campaigns),
        Page("/email-campaigns/1/edit", "email_campaigns", configure_email_campaigns),
    ],
    "namespaces": [
        Page("/namespaces", "namespaces"),
        Page("/namespaces/new", "namespaces"),
        Page("/namespaces/{namespace}", "namespaces", seed_namespace),
        Page("/namespaces/{namespace}/edit", "namespaces", seed_namespace),
    ],
    "prompts": [
        Page("/prompts", "prompts"),
        Page("/prompts/new", "prompts"),
        Page("/prompts/generate", "prompts", enable_openai),
        Page("/prompts/{prompt}", "prompts", seed_prompt),
        Page("/prompts/{prompt}/edit", "prompts", seed_prompt),
    ],
    "knowledge": [
        Page("/knowledge", "knowledge"),
        Page("/knowledge/new", "knowledge"),
        Page("/knowledge/generate", "knowledge", enable_openai),
        Page("/knowledge/{entry}", "knowledge", seed_entry),
        Page("/knowledge/{entry}/edit", "knowledge", seed_entry),
        Page("/knowledge/{entry}/validation", "knowledge", seed_entry),
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


async def _start_database(stack: AsyncExitStack, tmp_path) -> async_sessionmaker:
    """Replace the application's database by a SQLite file until the stack closes."""
    stack.enter_context(_sqlite_column_types())
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path}/internal.db")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    session_maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async def override_get_db():
        async with session_maker() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db
    stack.callback(app.dependency_overrides.pop, get_db, None)
    stack.push_async_callback(engine.dispose)
    return session_maker


@asynccontextmanager
async def running_app(tmp_path) -> AsyncIterator[Env]:
    """Run the application against SQLite with mocked clients and token exchange."""
    async with AsyncExitStack() as stack:
        session_maker = await _start_database(stack, tmp_path)

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
