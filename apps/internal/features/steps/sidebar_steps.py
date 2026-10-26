# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Step definitions asserting the admin sidebar rendered on a page."""

from html.parser import HTMLParser

from behave import given, then
from internal.auth.models import User
from internal.services.token_exchange import TokenExchangeError


class _SidebarParser(HTMLParser):
    """Collect the links of the ``admin-nav`` list and the user block."""

    def __init__(self) -> None:
        super().__init__()
        self.links: list[dict] = []
        self.user_email: str | None = None
        self._in_nav = False
        self._in_email = False

    def handle_starttag(self, tag, attrs):
        attributes = dict(attrs)
        classes = (attributes.get("class") or "").split()
        if tag == "ul" and "admin-nav" in classes:
            self._in_nav = True
        elif tag == "a" and self._in_nav:
            self.links.append({"href": attributes.get("href"), "active": "active" in classes})
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


def _sidebar(context) -> _SidebarParser:
    parser = _SidebarParser()
    parser.feed(context.response.text)
    return parser


@given('I am authenticated with only the scopes "{scopes}" granted by token exchange')
def step_authenticated_via_exchange(context, scopes):
    """Mimic production: the token only carries OIDC scopes, RBAC scopes come from the exchange.

    The exchange grants the requested scopes the user holds (wildcards included)
    and fails when none of them is held.
    """
    context.authenticated = True
    context.user_scopes = scopes
    context.configure_auth(context)
    rbac = User(id=context.user_id, scopes=scopes.split())

    claims = {
        "sub": context.user_id,
        "email": context.user_email,
        "name": context.user_name,
        "scope": "openid profile email",
    }
    context.mock_jwt_validate.return_value = claims
    context.mock_jwt_validate_introspect.return_value = claims

    async def _exchange(token, requested):
        granted = [scope for scope in requested if rbac.has_scope(scope)]
        if not granted:
            raise TokenExchangeError("insufficient_scope", error_code="insufficient_scope")
        return {"scope": " ".join(granted), "access_token": "exchanged-test-token"}

    context.mock_exchange_validate.side_effect = _exchange


@then('the sidebar should link to "{href}"')
def step_sidebar_links_to(context, href):
    hrefs = [link["href"] for link in _sidebar(context).links]
    assert href in hrefs, f"Sidebar has no link to '{href}'. Links: {hrefs}"


@then('the sidebar should not link to "{href}"')
def step_sidebar_not_links_to(context, href):
    hrefs = [link["href"] for link in _sidebar(context).links]
    assert href not in hrefs, f"Sidebar unexpectedly links to '{href}'. Links: {hrefs}"


@then('the active sidebar link should be "{href}"')
def step_sidebar_active_link(context, href):
    active = [link["href"] for link in _sidebar(context).links if link["active"]]
    assert active == [href], f"Expected the only active sidebar link to be '{href}', got {active}"


@then("the sidebar should list exactly these links")
def step_sidebar_lists_exactly(context):
    expected = sorted(row["href"] for row in context.table)
    actual = sorted(link["href"] for link in _sidebar(context).links)
    assert actual == expected, f"Expected sidebar links {expected}, got {actual}"


@then('the sidebar should show the user "{email}"')
def step_sidebar_user(context, email):
    actual = _sidebar(context).user_email
    assert actual == email, f"Expected sidebar user '{email}', got '{actual}'"


@then('the sidebar link to "{href}" should be {state}')
def step_sidebar_link_state(context, href, state):
    assert state in ("visible", "hidden"), f"Unknown state '{state}'"
    hrefs = [link["href"] for link in _sidebar(context).links]
    assert (href in hrefs) == (state == "visible"), (
        f"Expected the sidebar link to '{href}' to be {state}. Links: {hrefs}"
    )
