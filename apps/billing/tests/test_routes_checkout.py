# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for checkout session route (requires auth with billing:checkout:write)."""

from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest
from billing.config import settings
from billing.services.stripe_service import StripeService
from httpx import AsyncClient


@pytest.fixture
def saas_id():
    """Generate a consistent SaaS app ID."""
    return str(uuid4())


@pytest.fixture
def customer_id():
    """Generate a consistent customer ID."""
    return str(uuid4())


@pytest.fixture
def price_id():
    """Generate a consistent price ID."""
    return str(uuid4())


@pytest.fixture
def mock_saas_app_obj(saas_id):
    """Create a mock SaasApp."""
    app = MagicMock()
    app.id = saas_id
    app.slug = "test-app"
    app.is_active = True
    app.branding = None
    app.checkout_url_allowlist = ["https://example.com"]
    return app


@pytest.fixture
def mock_customer(customer_id, saas_id):
    """Create a mock Customer."""
    customer = MagicMock()
    customer.id = customer_id
    customer.saas_app_id = saas_id
    customer.external_id = "ext-user-123"
    customer.stripe_customer_id = "cus_test123"
    customer.email = "customer@example.com"
    customer.name = "Test Customer"
    customer.deleted_at = None
    return customer


@pytest.fixture
def mock_price(price_id):
    """Create a mock BillingPrice."""
    price = MagicMock()
    price.id = price_id
    price.stripe_price_id = "price_test123"
    price.currency = "usd"
    price.unit_amount = 1000
    price.is_active = True
    return price


@pytest.fixture
def mock_stripe_session():
    """Create a mock Stripe checkout session."""
    session = MagicMock()
    session.id = "cs_test_session123"
    session.url = "https://checkout.stripe.com/pay/cs_test_session123"
    return session


@pytest.fixture
def checkout_payload(saas_id, customer_id, price_id):
    """Create a valid checkout session request payload."""
    return {
        "saas_id": saas_id,
        "customer_id": customer_id,
        "price_id": price_id,
        "success_url": "https://example.com/success",
        "cancel_url": "https://example.com/cancel",
        "mode": "subscription",
        "quantity": 1,
    }


@pytest.fixture
def checkout_payload_external(saas_id, price_id):
    """Create a checkout payload using external_id instead of customer_id."""
    return {
        "saas_id": saas_id,
        "external_id": "ext-user-123",
        "price_id": price_id,
        "success_url": "https://example.com/success",
        "cancel_url": "https://example.com/cancel",
        "mode": "subscription",
        "quantity": 1,
    }


def _setup_checkout_db_mock(mock_db_session, saas_app, customer, price):
    """Helper to set up mock db for checkout endpoint.

    Up to 3 execute calls depending on the flow:
    1. SaasApp lookup
    2. Customer lookup
    3. Price lookup
    """
    results = []

    # 1. SaasApp lookup
    mock_saas_result = MagicMock()
    mock_saas_result.scalar_one_or_none.return_value = saas_app
    results.append(mock_saas_result)

    # 2. Customer lookup (may be None for auto-create flow)
    if customer is not None or saas_app is not None:
        mock_cust_result = MagicMock()
        mock_cust_result.scalar_one_or_none.return_value = customer
        results.append(mock_cust_result)

    # 3. Price lookup
    if price is not None:
        mock_price_result = MagicMock()
        mock_price_result.scalar_one_or_none.return_value = price
        results.append(mock_price_result)

    mock_db_session.execute.side_effect = results


class TestCreateCheckoutSession:
    """Tests for POST /checkout/session endpoint."""

    @pytest.mark.asyncio
    @patch("billing.routes.checkout.get_stripe_service")
    async def test_checkout_success_with_customer_id(
        self,
        mock_get_stripe,
        auth_client: AsyncClient,
        mock_db_session,
        mock_saas_app_obj,
        mock_customer,
        mock_price,
        mock_stripe_session,
        checkout_payload,
    ):
        """POST /checkout/session with customer_id should return session."""
        mock_stripe_service = MagicMock()
        mock_stripe_service.create_checkout_session.return_value = mock_stripe_session
        mock_get_stripe.return_value = mock_stripe_service

        _setup_checkout_db_mock(mock_db_session, mock_saas_app_obj, mock_customer, mock_price)

        response = await auth_client.post("/checkout/session", json=checkout_payload)

        assert response.status_code == 200
        data = response.json()
        assert data["session_id"] == "cs_test_session123"
        assert data["url"] == "https://checkout.stripe.com/pay/cs_test_session123"

    @pytest.mark.asyncio
    @patch("billing.routes.checkout.get_stripe_service")
    async def test_checkout_success_with_external_id(
        self,
        mock_get_stripe,
        auth_client: AsyncClient,
        mock_db_session,
        mock_saas_app_obj,
        mock_customer,
        mock_price,
        mock_stripe_session,
        checkout_payload_external,
    ):
        """POST /checkout/session with external_id should return session."""
        mock_stripe_service = MagicMock()
        mock_stripe_service.create_checkout_session.return_value = mock_stripe_session
        mock_get_stripe.return_value = mock_stripe_service

        _setup_checkout_db_mock(mock_db_session, mock_saas_app_obj, mock_customer, mock_price)

        response = await auth_client.post("/checkout/session", json=checkout_payload_external)

        assert response.status_code == 200
        data = response.json()
        assert data["session_id"] == "cs_test_session123"
        assert data["url"] == "https://checkout.stripe.com/pay/cs_test_session123"

    @pytest.mark.asyncio
    @patch("billing.routes.checkout.get_stripe_service")
    async def test_checkout_auto_create_customer(
        self,
        mock_get_stripe,
        auth_client: AsyncClient,
        mock_db_session,
        mock_saas_app_obj,
        mock_price,
        mock_stripe_session,
        saas_id,
        price_id,
    ):
        """POST /checkout/session should auto-create customer when external_id + email provided."""
        # Stripe service for both customer creation and checkout
        mock_stripe_customer = MagicMock()
        mock_stripe_customer.id = "cus_new_auto"

        mock_stripe_service = MagicMock()
        mock_stripe_service.create_customer.return_value = mock_stripe_customer
        mock_stripe_service.create_checkout_session.return_value = mock_stripe_session
        mock_get_stripe.return_value = mock_stripe_service

        # DB side_effect:
        # 1. SaasApp lookup -> found
        # 2. Customer lookup by external_id -> not found (None)
        # 3. Price lookup -> found
        mock_saas_result = MagicMock()
        mock_saas_result.scalar_one_or_none.return_value = mock_saas_app_obj

        mock_cust_result = MagicMock()
        mock_cust_result.scalar_one_or_none.return_value = None  # Not found

        mock_price_result = MagicMock()
        mock_price_result.scalar_one_or_none.return_value = mock_price

        mock_db_session.execute.side_effect = [
            mock_saas_result,
            mock_cust_result,
            mock_price_result,
        ]

        payload = {
            "saas_id": saas_id,
            "external_id": "new-ext-user",
            "price_id": price_id,
            "success_url": "https://example.com/success",
            "cancel_url": "https://example.com/cancel",
            "customer_email": "new@example.com",
            "customer_name": "New User",
        }

        response = await auth_client.post("/checkout/session", json=payload)

        assert response.status_code == 200
        data = response.json()
        assert data["session_id"] == "cs_test_session123"

        # Verify customer was created in Stripe
        mock_stripe_service.create_customer.assert_called_once()

        # Verify customer was added to DB
        mock_db_session.add.assert_called_once()
        mock_db_session.flush.assert_called()

    @pytest.mark.asyncio
    @patch("billing.routes.checkout.get_stripe_service")
    async def test_checkout_saas_app_not_found(
        self,
        mock_get_stripe,
        auth_client: AsyncClient,
        mock_db_session,
        checkout_payload,
    ):
        """POST /checkout/session should return 404 when SaaS app not found."""
        mock_saas_result = MagicMock()
        mock_saas_result.scalar_one_or_none.return_value = None
        mock_db_session.execute.side_effect = [mock_saas_result]

        response = await auth_client.post("/checkout/session", json=checkout_payload)

        assert response.status_code == 404
        assert "SaaS app not found" in response.json()["detail"]

    @pytest.mark.asyncio
    @patch("billing.routes.checkout.get_stripe_service")
    async def test_checkout_customer_not_found_no_email(
        self,
        mock_get_stripe,
        auth_client: AsyncClient,
        mock_db_session,
        mock_saas_app_obj,
        saas_id,
        price_id,
    ):
        """POST /checkout/session should return 404 when customer not found and no email for auto-create."""
        mock_stripe_service = MagicMock()
        mock_get_stripe.return_value = mock_stripe_service

        # DB side_effect:
        # 1. SaasApp -> found
        # 2. Customer by external_id -> None
        mock_saas_result = MagicMock()
        mock_saas_result.scalar_one_or_none.return_value = mock_saas_app_obj

        mock_cust_result = MagicMock()
        mock_cust_result.scalar_one_or_none.return_value = None

        mock_db_session.execute.side_effect = [mock_saas_result, mock_cust_result]

        payload = {
            "saas_id": saas_id,
            "external_id": "nonexistent-user",
            "price_id": price_id,
            "success_url": "https://example.com/success",
            "cancel_url": "https://example.com/cancel",
            # No customer_email -> cannot auto-create
        }

        response = await auth_client.post("/checkout/session", json=payload)

        assert response.status_code == 404
        assert "Customer not found" in response.json()["detail"]

    @pytest.mark.asyncio
    @patch("billing.routes.checkout.get_stripe_service")
    async def test_checkout_price_not_found(
        self,
        mock_get_stripe,
        auth_client: AsyncClient,
        mock_db_session,
        mock_saas_app_obj,
        mock_customer,
        checkout_payload,
    ):
        """POST /checkout/session should return 404 when price not found."""
        mock_stripe_service = MagicMock()
        mock_get_stripe.return_value = mock_stripe_service

        # DB side_effect:
        # 1. SaasApp -> found
        # 2. Customer -> found
        # 3. Price -> None
        mock_saas_result = MagicMock()
        mock_saas_result.scalar_one_or_none.return_value = mock_saas_app_obj

        mock_cust_result = MagicMock()
        mock_cust_result.scalar_one_or_none.return_value = mock_customer

        mock_price_result = MagicMock()
        mock_price_result.scalar_one_or_none.return_value = None

        mock_db_session.execute.side_effect = [
            mock_saas_result,
            mock_cust_result,
            mock_price_result,
        ]

        response = await auth_client.post("/checkout/session", json=checkout_payload)

        assert response.status_code == 404
        assert "Price not found" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_checkout_requires_auth(
        self,
        client: AsyncClient,
        checkout_payload,
    ):
        """POST /checkout/session should return 401 without authentication."""
        response = await client.post("/checkout/session", json=checkout_payload)

        assert response.status_code == 401

    @pytest.mark.asyncio
    @patch("billing.routes.checkout.get_stripe_service")
    async def test_checkout_no_customer_id_no_external_id(
        self,
        mock_get_stripe,
        auth_client: AsyncClient,
        mock_db_session,
        mock_saas_app_obj,
        saas_id,
        price_id,
    ):
        """POST /checkout/session without customer_id or external_id should return 404."""
        mock_get_stripe.return_value = MagicMock()

        mock_saas_result = MagicMock()
        mock_saas_result.scalar_one_or_none.return_value = mock_saas_app_obj
        mock_db_session.execute.side_effect = [mock_saas_result]

        payload = {
            "saas_id": saas_id,
            "price_id": price_id,
            "success_url": "https://example.com/success",
            "cancel_url": "https://example.com/cancel",
        }

        response = await auth_client.post("/checkout/session", json=payload)

        assert response.status_code == 404
        assert "Customer not found" in response.json()["detail"]


class TestCheckoutIsolation:
    """A checkout never mixes the data of two SaaS apps."""

    @pytest.mark.asyncio
    @patch("billing.routes.checkout.get_stripe_service")
    async def test_price_lookup_is_scoped_to_the_saas_app(
        self,
        mock_get_stripe,
        auth_client: AsyncClient,
        mock_db_session,
        mock_saas_app_obj,
        mock_customer,
        mock_price,
        mock_stripe_session,
        checkout_payload,
        saas_id,
    ):
        """The price query joins the product and filters on the requested SaaS app."""
        mock_get_stripe.return_value.create_checkout_session.return_value = mock_stripe_session
        _setup_checkout_db_mock(mock_db_session, mock_saas_app_obj, mock_customer, mock_price)

        response = await auth_client.post("/checkout/session", json=checkout_payload)

        assert response.status_code == 200
        price_query = mock_db_session.execute.call_args_list[-1][0][0]
        compiled = price_query.compile()
        sql = str(compiled)
        assert "billing_products.saas_app_id" in sql
        assert "billing_prices.is_active" in sql
        assert saas_id in compiled.params.values()

    @pytest.mark.asyncio
    @patch("billing.routes.checkout.get_stripe_service")
    async def test_price_of_another_saas_app_is_reported_as_unknown(
        self,
        mock_get_stripe,
        auth_client: AsyncClient,
        mock_db_session,
        mock_saas_app_obj,
        mock_customer,
        checkout_payload,
    ):
        """The scoped query finds nothing for a foreign price: 404, Stripe is not called."""
        _setup_checkout_db_mock(mock_db_session, mock_saas_app_obj, mock_customer, None)
        empty = MagicMock()
        empty.scalar_one_or_none.return_value = None
        mock_db_session.execute.side_effect = [
            *mock_db_session.execute.side_effect,
            empty,
        ]

        response = await auth_client.post("/checkout/session", json=checkout_payload)

        assert response.status_code == 404
        assert "Price not found" in response.json()["detail"]
        mock_get_stripe.return_value.create_checkout_session.assert_not_called()

    @pytest.mark.asyncio
    async def test_caller_metadata_cannot_override_saas_id(
        self,
        auth_client: AsyncClient,
        mock_db_session,
        mock_saas_app_obj,
        mock_customer,
        mock_price,
        checkout_payload,
        saas_id,
    ):
        """With the real Stripe service, the saas_id sent to Stripe is the server's."""
        _setup_checkout_db_mock(mock_db_session, mock_saas_app_obj, mock_customer, mock_price)
        checkout_payload["metadata"] = {"saas_id": "forged", "campaign": "spring"}

        with (
            patch("billing.services.stripe_service.stripe") as mock_stripe,
            patch("billing.routes.checkout.get_stripe_service", return_value=StripeService()),
        ):
            mock_stripe.checkout.Session.create.return_value = MagicMock(id="cs_1", url="u")
            response = await auth_client.post("/checkout/session", json=checkout_payload)

        assert response.status_code == 200
        params = mock_stripe.checkout.Session.create.call_args[1]
        assert params["metadata"] == {"saas_id": saas_id, "campaign": "spring"}
        assert params["subscription_data"]["metadata"] == {"saas_id": saas_id}


class TestCheckoutRedirects:
    """Success and cancel URLs must be allowed by the SaaS app."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize("field", ["success_url", "cancel_url"])
    @patch("billing.routes.checkout.get_stripe_service")
    async def test_url_outside_the_allowlist_is_refused(
        self,
        mock_get_stripe,
        field,
        auth_client: AsyncClient,
        mock_db_session,
        mock_saas_app_obj,
        checkout_payload,
    ):
        mock_saas_result = MagicMock()
        mock_saas_result.scalar_one_or_none.return_value = mock_saas_app_obj
        mock_db_session.execute.side_effect = [mock_saas_result]
        checkout_payload[field] = "https://evil.test/landing"

        response = await auth_client.post("/checkout/session", json=checkout_payload)

        assert response.status_code == 422
        assert field in response.json()["detail"]
        mock_get_stripe.return_value.create_checkout_session.assert_not_called()

    @pytest.mark.asyncio
    @patch("billing.routes.checkout.get_stripe_service")
    async def test_saas_app_without_allowlist_is_refused_by_default(
        self,
        mock_get_stripe,
        auth_client: AsyncClient,
        mock_db_session,
        mock_saas_app_obj,
        checkout_payload,
    ):
        mock_saas_app_obj.checkout_url_allowlist = None
        mock_saas_result = MagicMock()
        mock_saas_result.scalar_one_or_none.return_value = mock_saas_app_obj
        mock_db_session.execute.side_effect = [mock_saas_result]

        response = await auth_client.post("/checkout/session", json=checkout_payload)

        assert response.status_code == 422
        assert "checkout_url_allowlist" in response.json()["detail"]

    @pytest.mark.asyncio
    @patch("billing.routes.checkout.get_stripe_service")
    async def test_missing_allowlist_can_be_tolerated_by_configuration(
        self,
        mock_get_stripe,
        auth_client: AsyncClient,
        mock_db_session,
        mock_saas_app_obj,
        mock_customer,
        mock_price,
        mock_stripe_session,
        checkout_payload,
        monkeypatch,
    ):
        monkeypatch.setattr(settings, "redirect_allowlist_required", False)
        mock_saas_app_obj.checkout_url_allowlist = None
        mock_get_stripe.return_value.create_checkout_session.return_value = mock_stripe_session
        _setup_checkout_db_mock(mock_db_session, mock_saas_app_obj, mock_customer, mock_price)

        response = await auth_client.post("/checkout/session", json=checkout_payload)

        assert response.status_code == 200


class TestCheckoutBranding:
    """The branding of the SaaS app customizes the hosted page."""

    @pytest.mark.asyncio
    @patch("billing.routes.checkout.get_stripe_service")
    async def test_locale_and_custom_text_are_forwarded(
        self,
        mock_get_stripe,
        auth_client: AsyncClient,
        mock_db_session,
        mock_saas_app_obj,
        mock_customer,
        mock_price,
        mock_stripe_session,
        checkout_payload,
    ):
        mock_saas_app_obj.branding = {
            "locale": "fr",
            "custom_text": {"submit": {"message": "Thanks"}},
            "color": "#000",
        }
        service = mock_get_stripe.return_value
        service.create_checkout_session.return_value = mock_stripe_session
        _setup_checkout_db_mock(mock_db_session, mock_saas_app_obj, mock_customer, mock_price)

        response = await auth_client.post("/checkout/session", json=checkout_payload)

        assert response.status_code == 200
        kwargs = service.create_checkout_session.call_args.kwargs
        assert kwargs["locale"] == "fr"
        assert kwargs["custom_text"] == {"submit": {"message": "Thanks"}}

    @pytest.mark.asyncio
    @patch("billing.routes.checkout.get_stripe_service")
    async def test_malformed_branding_is_ignored(
        self,
        mock_get_stripe,
        auth_client: AsyncClient,
        mock_db_session,
        mock_saas_app_obj,
        mock_customer,
        mock_price,
        mock_stripe_session,
        checkout_payload,
    ):
        mock_saas_app_obj.branding = {"locale": 12, "custom_text": "text"}
        service = mock_get_stripe.return_value
        service.create_checkout_session.return_value = mock_stripe_session
        _setup_checkout_db_mock(mock_db_session, mock_saas_app_obj, mock_customer, mock_price)

        await auth_client.post("/checkout/session", json=checkout_payload)

        kwargs = service.create_checkout_session.call_args.kwargs
        assert kwargs["locale"] is None
        assert kwargs["custom_text"] is None


class TestCheckoutBounds:
    """Quantity and trial period bounds come from the settings."""

    @pytest.mark.asyncio
    async def test_quantity_above_the_maximum_is_rejected(
        self, auth_client: AsyncClient, checkout_payload
    ):
        checkout_payload["quantity"] = settings.checkout_max_quantity + 1

        response = await auth_client.post("/checkout/session", json=checkout_payload)

        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_trial_above_the_maximum_is_rejected(
        self, auth_client: AsyncClient, checkout_payload
    ):
        checkout_payload["trial_period_days"] = settings.max_trial_period_days + 1

        response = await auth_client.post("/checkout/session", json=checkout_payload)

        assert response.status_code == 422
