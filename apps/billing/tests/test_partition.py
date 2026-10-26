# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for the partitioning of the API between SaaS applications.

The first half tests the guard on its own; the second half drives real HTTP
requests through the routes of the platform, usage, checkout and plans with
two SaaS applications (A and B) and clients bound to one of them.
"""

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from billing.auth import AuthContext
from billing.auth.models import User
from billing.config import settings
from billing.partition import PartitionGuard
from fastapi import HTTPException

ADMIN_SCOPE = "billing:admin"
PLATFORM = ["billing:platform:read", "billing:platform:write"]
USAGE = ["billing:usage:write"]
CHECKOUT = ["billing:checkout:write"]


def _bindings(*saas_ids: str) -> MagicMock:
    """Result of the binding query: the SaaS identifiers a client is bound to."""
    result = MagicMock()
    result.scalars.return_value.all.return_value = list(saas_ids)
    return result


def _one(value) -> MagicMock:
    result = MagicMock()
    result.scalar_one_or_none.return_value = value
    return result


def _context(client_id: str | None, scopes: list[str]) -> AuthContext:
    user = User(id="u-1", scopes=scopes, client_id=client_id)
    return AuthContext(user=user, client_id=client_id, token_scopes=scopes)


@pytest.fixture
def saas_a() -> str:
    return str(uuid4())


@pytest.fixture
def saas_b() -> str:
    return str(uuid4())


@pytest.fixture
def guard() -> PartitionGuard:
    return PartitionGuard(admin_scope=ADMIN_SCOPE, allow_unbound=False)


@pytest.fixture
def db() -> AsyncMock:
    session = AsyncMock()
    session.execute = AsyncMock()
    return session


class TestPartitionGuard:
    """The guard decides from the client id, its bindings and the admin scope."""

    @pytest.mark.asyncio
    async def test_bound_client_may_act_on_its_saas(self, guard, db, saas_a):
        db.execute.return_value = _bindings(saas_a)

        await guard.authorize(_context("client-a", PLATFORM), saas_a, db)

    @pytest.mark.asyncio
    async def test_bound_client_is_refused_on_another_saas(self, guard, db, saas_a, saas_b):
        db.execute.return_value = _bindings(saas_a)

        with pytest.raises(HTTPException) as exc_info:
            await guard.authorize(_context("client-a", PLATFORM), saas_b, db)

        assert exc_info.value.status_code == 403

    @pytest.mark.asyncio
    async def test_client_bound_to_several_saas(self, guard, db, saas_a, saas_b):
        db.execute.return_value = _bindings(saas_a, saas_b)

        await guard.authorize(_context("client-ab", PLATFORM), saas_a, db)
        await guard.authorize(_context("client-ab", PLATFORM), saas_b, db)

    @pytest.mark.asyncio
    async def test_unbound_client_is_denied_by_default(self, guard, db, saas_a):
        db.execute.return_value = _bindings()

        with pytest.raises(HTTPException) as exc_info:
            await guard.authorize(_context("client-x", PLATFORM), saas_a, db)

        assert exc_info.value.status_code == 403

    @pytest.mark.asyncio
    async def test_unbound_client_is_allowed_in_legacy_mode(self, db, saas_a):
        legacy = PartitionGuard(admin_scope=ADMIN_SCOPE, allow_unbound=True)
        db.execute.return_value = _bindings()

        await legacy.authorize(_context("client-x", PLATFORM), saas_a, db)

    @pytest.mark.asyncio
    async def test_legacy_mode_does_not_free_a_bound_client(self, db, saas_a, saas_b):
        """A client that has at least one binding is always held to its bindings."""
        legacy = PartitionGuard(admin_scope=ADMIN_SCOPE, allow_unbound=True)
        db.execute.return_value = _bindings(saas_a)

        with pytest.raises(HTTPException):
            await legacy.authorize(_context("client-a", PLATFORM), saas_b, db)

    @pytest.mark.asyncio
    async def test_admin_scope_crosses_saas_without_a_query(self, guard, db, saas_a, saas_b):
        admin = _context("client-admin", [*PLATFORM, ADMIN_SCOPE])

        await guard.authorize(admin, saas_a, db)
        await guard.authorize(admin, saas_b, db)

        db.execute.assert_not_called()

    @pytest.mark.asyncio
    async def test_wildcard_scope_is_admin(self, guard, db, saas_a):
        await guard.authorize(_context("client-root", ["billing:*"]), saas_a, db)

        db.execute.assert_not_called()

    @pytest.mark.asyncio
    async def test_admin_scope_name_is_configurable(self, db, saas_a):
        custom = PartitionGuard(admin_scope="ops:billing", allow_unbound=False)
        db.execute.return_value = _bindings()

        await custom.authorize(_context("client-ops", ["ops:billing"]), saas_a, db)
        with pytest.raises(HTTPException):
            await custom.authorize(_context("client-ops", [ADMIN_SCOPE]), saas_a, db)

    @pytest.mark.asyncio
    async def test_token_without_client_is_denied(self, guard, db, saas_a):
        with pytest.raises(HTTPException) as exc_info:
            await guard.authorize(_context(None, PLATFORM), saas_a, db)

        assert exc_info.value.status_code == 403
        db.execute.assert_not_called()

    @pytest.mark.asyncio
    async def test_admin_scope_must_be_in_the_token_not_in_the_route_scopes(
        self, guard, db, saas_a
    ):
        """Scopes reduced to the route's own (token exchange) do not make an admin."""
        user = User(id="u-1", scopes=[ADMIN_SCOPE], client_id="client-x")
        context = AuthContext(user=user, client_id="client-x", token_scopes=PLATFORM)
        db.execute.return_value = _bindings()

        with pytest.raises(HTTPException):
            await guard.authorize(context, saas_a, db)

    @pytest.mark.asyncio
    async def test_authorized_saas_ids(self, guard, db, saas_a):
        db.execute.return_value = _bindings(saas_a)

        assert await guard.authorized_saas_ids(_context("client-a", PLATFORM), db) == {saas_a}
        assert await guard.authorized_saas_ids(_context(None, PLATFORM), db) == set()
        assert await guard.authorized_saas_ids(_context("c", [*PLATFORM, ADMIN_SCOPE]), db) is None

    def test_default_guard_reads_the_settings(self, monkeypatch):
        from billing.partition import get_partition_guard

        monkeypatch.setattr(settings, "partition_admin_scope", "ops:billing")
        monkeypatch.setattr(settings, "partition_allow_unbound", True)

        built = get_partition_guard()

        assert (built.admin_scope, built.allow_unbound) == ("ops:billing", True)


class TestSettingsDefaults:
    def test_secure_by_default(self):
        from billing.config import Settings

        defaults = Settings(_env_file=None)

        assert defaults.partition_admin_scope == "billing:admin"
        assert defaults.partition_allow_unbound is False
        assert defaults.plans_public is False


class TestPlatformIsolation:
    """A client bound to SaaS A cannot touch the platform data of SaaS B."""

    @pytest.mark.asyncio
    async def test_own_saas_is_served(self, partitioned_client_factory, mock_db_session, saas_a):
        client = await partitioned_client_factory("client-a", PLATFORM)
        saas = MagicMock(id=saas_a)
        listing = MagicMock()
        listing.scalars.return_value.all.return_value = []
        mock_db_session.execute.side_effect = [_bindings(saas_a), _one(saas), listing]

        response = await client.get(f"/platform/{saas_a}/products")

        assert response.status_code == 200

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("method", "path"),
        [
            ("get", "/platform/{b}/products"),
            ("get", "/platform/{b}/products/{x}"),
            ("post", "/platform/{b}/products"),
            ("get", "/platform/{b}/products/{x}/prices"),
            ("get", "/platform/{b}/customers"),
            ("get", "/platform/{b}/customers/{x}"),
            ("get", "/platform/{b}/customers/{x}/portal?return_url=https://example.test"),
            ("get", "/platform/{b}/subscriptions"),
            ("get", "/platform/{b}/subscriptions/{x}"),
            ("post", "/platform/{b}/subscriptions/{x}/cancel"),
            ("post", "/platform/{b}/subscriptions/{x}/reactivate"),
            ("delete", "/platform/{b}/subscriptions/{x}"),
            ("get", "/platform/{b}/external/{x}/subscription"),
            ("get", "/platform/saas/{b}"),
            ("patch", "/platform/saas/{b}"),
            ("post", "/platform/saas/{b}/sync-stripe"),
        ],
    )
    async def test_other_saas_is_refused_before_the_route_runs(
        self, partitioned_client_factory, mock_db_session, saas_a, saas_b, method, path
    ):
        client = await partitioned_client_factory("client-a", PLATFORM)
        mock_db_session.execute.side_effect = [_bindings(saas_a)]
        url = path.format(b=saas_b, x=uuid4())
        body = {"json": {"name": "x"}} if method in ("post", "patch") else {}

        response = await getattr(client, method)(url, **body)

        assert response.status_code == 403
        assert "not authorized" in response.json()["detail"]
        # Only the binding lookup ran: no data of SaaS B was read or written
        assert mock_db_session.execute.call_count == 1
        mock_db_session.add.assert_not_called()

    @pytest.mark.asyncio
    async def test_unbound_client_is_denied_everywhere(
        self, partitioned_client_factory, mock_db_session, saas_a
    ):
        client = await partitioned_client_factory("client-new", PLATFORM)
        mock_db_session.execute.side_effect = [_bindings()]

        response = await client.get(f"/platform/{saas_a}/products")

        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_token_without_client_id_is_denied(
        self, partitioned_client_factory, mock_db_session, saas_a
    ):
        client = await partitioned_client_factory(None, PLATFORM)

        response = await client.get(f"/platform/{saas_a}/products")

        assert response.status_code == 403
        assert "client" in response.json()["detail"]
        mock_db_session.execute.assert_not_called()

    @pytest.mark.asyncio
    async def test_admin_scope_may_cross_saas(
        self, partitioned_client_factory, mock_db_session, saas_a, saas_b
    ):
        client = await partitioned_client_factory("client-admin", [*PLATFORM, ADMIN_SCOPE])
        listing = MagicMock()
        listing.scalars.return_value.all.return_value = []
        mock_db_session.execute.side_effect = [
            _one(MagicMock(id=saas_a)),
            listing,
            _one(MagicMock(id=saas_b)),
            listing,
        ]

        first = await client.get(f"/platform/{saas_a}/products")
        second = await client.get(f"/platform/{saas_b}/products")

        assert (first.status_code, second.status_code) == (200, 200)

    @pytest.mark.asyncio
    async def test_missing_scope_is_still_required(
        self, partitioned_client_factory, mock_db_session, saas_a
    ):
        """Being bound does not replace the scopes."""
        client = await partitioned_client_factory("client-a", USAGE)

        response = await client.get(f"/platform/{saas_a}/products")

        assert response.status_code == 403
        assert "scope" in response.json()["detail"].lower()
        mock_db_session.execute.assert_not_called()

    @pytest.mark.asyncio
    async def test_unknown_saas_looks_like_an_unauthorized_one(
        self, partitioned_client_factory, mock_db_session, saas_a
    ):
        """A client cannot probe which SaaS identifiers exist."""
        client = await partitioned_client_factory("client-a", PLATFORM)
        mock_db_session.execute.side_effect = [_bindings(saas_a)]

        response = await client.get(f"/platform/{uuid4()}/products")

        assert response.status_code == 403


class TestSaasListingAndCreation:
    """Cross-application operations of /platform/saas."""

    @pytest.mark.asyncio
    async def test_listing_is_restricted_to_the_bound_saas(
        self, partitioned_client_factory, mock_db_session, saas_a
    ):
        client = await partitioned_client_factory("client-a", PLATFORM)
        listing = MagicMock()
        listing.scalars.return_value.all.return_value = []
        mock_db_session.execute.side_effect = [_bindings(saas_a), listing]

        response = await client.get("/platform/saas")

        assert response.status_code == 200
        query = mock_db_session.execute.call_args_list[-1][0][0].compile()
        assert " IN " in str(query)
        assert saas_a in str(query.params.values())

    @pytest.mark.asyncio
    async def test_unbound_client_lists_nothing_without_querying_saas(
        self, partitioned_client_factory, mock_db_session
    ):
        client = await partitioned_client_factory("client-new", PLATFORM)
        mock_db_session.execute.side_effect = [_bindings()]

        response = await client.get("/platform/saas")

        assert response.status_code == 200
        assert response.json() == []
        assert mock_db_session.execute.call_count == 1

    @pytest.mark.asyncio
    async def test_admin_lists_every_saas(self, partitioned_client_factory, mock_db_session):
        client = await partitioned_client_factory("client-admin", [*PLATFORM, ADMIN_SCOPE])
        listing = MagicMock()
        listing.scalars.return_value.all.return_value = []
        mock_db_session.execute.side_effect = [listing]

        response = await client.get("/platform/saas")

        assert response.status_code == 200
        query = mock_db_session.execute.call_args_list[-1][0][0].compile()
        assert " IN " not in str(query)

    @pytest.mark.asyncio
    async def test_creating_a_saas_requires_the_admin_scope(
        self, partitioned_client_factory, mock_db_session
    ):
        client = await partitioned_client_factory("client-a", PLATFORM)

        response = await client.post("/platform/saas", json={"name": "N", "slug": "n"})

        assert response.status_code == 403
        mock_db_session.add.assert_not_called()

    @pytest.mark.asyncio
    async def test_admin_can_create_a_saas(self, partitioned_client_factory, mock_db_session):
        client = await partitioned_client_factory("client-admin", [ADMIN_SCOPE])
        mock_db_session.execute.side_effect = [_one(None)]

        response = await client.post("/platform/saas", json={"name": "N", "slug": "n"})

        assert response.status_code == 201


class TestUsageIsolation:
    @pytest.mark.asyncio
    @pytest.mark.parametrize("endpoint", ["report", "batch"])
    async def test_other_saas_is_refused(
        self, partitioned_client_factory, mock_db_session, saas_a, saas_b, endpoint
    ):
        client = await partitioned_client_factory("client-a", USAGE)
        mock_db_session.execute.side_effect = [_bindings(saas_a)]
        event = {"subscription_id": str(uuid4()), "quantity": 1}
        body = event if endpoint == "report" else {"events": [event]}

        response = await client.post(f"/usage/{saas_b}/{endpoint}", json=body)

        assert response.status_code == 403
        assert mock_db_session.execute.call_count == 1
        mock_db_session.add.assert_not_called()

    @pytest.mark.asyncio
    async def test_own_saas_is_served(self, partitioned_client_factory, mock_db_session, saas_a):
        client = await partitioned_client_factory("client-a", USAGE)
        subscription = MagicMock(id=str(uuid4()), stripe_subscription_item_id="si_1")
        mock_db_session.execute.side_effect = [
            _bindings(saas_a),
            _one(MagicMock(id=saas_a)),
            _one(subscription),
        ]

        response = await client.post(
            f"/usage/{saas_a}/report", json={"subscription_id": subscription.id, "quantity": 3}
        )

        assert response.status_code == 201


class TestCheckoutIsolation:
    def _payload(self, saas_id: str) -> dict:
        return {
            "saas_id": saas_id,
            "customer_id": str(uuid4()),
            "price_id": str(uuid4()),
            "success_url": "https://example.com/ok",
            "cancel_url": "https://example.com/ko",
        }

    @pytest.mark.asyncio
    async def test_other_saas_is_refused_before_anything_is_read(
        self, partitioned_client_factory, mock_db_session, saas_a, saas_b
    ):
        client = await partitioned_client_factory("client-a", CHECKOUT)
        mock_db_session.execute.side_effect = [_bindings(saas_a)]

        response = await client.post("/checkout/session", json=self._payload(saas_b))

        assert response.status_code == 403
        assert mock_db_session.execute.call_count == 1

    @pytest.mark.asyncio
    async def test_unbound_client_is_denied(
        self, partitioned_client_factory, mock_db_session, saas_a
    ):
        client = await partitioned_client_factory("client-new", CHECKOUT)
        mock_db_session.execute.side_effect = [_bindings()]

        response = await client.post("/checkout/session", json=self._payload(saas_a))

        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_bound_client_reaches_the_route(
        self, partitioned_client_factory, mock_db_session, saas_a
    ):
        """Past the guard the route runs (here it stops on the unknown SaaS app)."""
        client = await partitioned_client_factory("client-a", CHECKOUT)
        mock_db_session.execute.side_effect = [_bindings(saas_a), _one(None)]

        response = await client.post("/checkout/session", json=self._payload(saas_a))

        assert response.status_code == 404
        assert "SaaS app not found" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_admin_scope_may_create_sessions_for_any_saas(
        self, partitioned_client_factory, mock_db_session, saas_b
    ):
        client = await partitioned_client_factory("client-admin", [*CHECKOUT, ADMIN_SCOPE])
        mock_db_session.execute.side_effect = [_one(None)]

        response = await client.post("/checkout/session", json=self._payload(saas_b))

        assert response.status_code == 404  # reached the route, no binding lookup


class TestPlansPartitioning:
    """The plans need a token and a binding unless PLANS_PUBLIC is enabled."""

    def _saas(self, saas_id: str, slug: str) -> MagicMock:
        return MagicMock(id=saas_id, slug=slug, is_active=True)

    @pytest.mark.asyncio
    async def test_anonymous_request_is_refused_by_default(self, client):
        response = await client.get("/plans/some-app")

        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_anonymous_request_is_served_when_public(
        self, client, mock_db_session, monkeypatch
    ):
        monkeypatch.setattr(settings, "plans_public", True)
        products = MagicMock()
        products.scalars.return_value.all.return_value = []
        mock_db_session.execute.side_effect = [_one(self._saas(str(uuid4()), "some-app")), products]

        response = await client.get("/plans/some-app")

        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_bound_client_reads_its_plans(
        self, partitioned_client_factory, mock_db_session, saas_a
    ):
        client = await partitioned_client_factory("client-a", PLATFORM)
        products = MagicMock()
        products.scalars.return_value.all.return_value = []
        mock_db_session.execute.side_effect = [
            _one(self._saas(saas_a, "app-a")),
            _bindings(saas_a),
            products,
        ]

        response = await client.get("/plans/app-a")

        assert response.status_code == 200
        assert response.json()["app_slug"] == "app-a"

    @pytest.mark.asyncio
    async def test_other_saas_plans_look_unknown(
        self, partitioned_client_factory, mock_db_session, saas_a, saas_b
    ):
        client = await partitioned_client_factory("client-a", PLATFORM)
        mock_db_session.execute.side_effect = [
            _one(self._saas(saas_b, "app-b")),
            _bindings(saas_a),
        ]

        response = await client.get("/plans/app-b")

        assert response.status_code == 404
        assert mock_db_session.execute.call_count == 2

    @pytest.mark.asyncio
    async def test_unbound_client_sees_no_plans(
        self, partitioned_client_factory, mock_db_session, saas_a
    ):
        client = await partitioned_client_factory("client-new", PLATFORM)
        mock_db_session.execute.side_effect = [
            _one(self._saas(saas_a, "app-a")),
            _bindings(),
        ]

        response = await client.get("/plans/app-a")

        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_token_needs_the_platform_read_scope(
        self, partitioned_client_factory, mock_db_session
    ):
        client = await partitioned_client_factory("client-a", USAGE)

        response = await client.get("/plans/app-a")

        assert response.status_code == 403
        mock_db_session.execute.assert_not_called()

    @pytest.mark.asyncio
    async def test_admin_reads_any_plans(self, partitioned_client_factory, mock_db_session, saas_b):
        client = await partitioned_client_factory("client-admin", [*PLATFORM, ADMIN_SCOPE])
        products = MagicMock()
        products.scalars.return_value.all.return_value = []
        mock_db_session.execute.side_effect = [_one(self._saas(saas_b, "app-b")), products]

        response = await client.get("/plans/app-b")

        assert response.status_code == 200
