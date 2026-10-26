# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for webhook routes."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from billing.config import settings
from billing.models.subscription import SubscriptionStatus
from billing.routes.webhooks import (
    get_customer_by_stripe_id,
    get_subscription_by_stripe_id,
    handle_checkout_session_completed,
    handle_customer_created,
    handle_customer_deleted,
    handle_customer_updated,
    handle_invoice_paid,
    handle_invoice_payment_failed,
    handle_subscription_deleted,
    handle_subscription_updated,
)


def _mock_result(value):
    r = MagicMock()
    r.scalar_one_or_none.return_value = value
    return r


class TestHelperFunctions:
    @pytest.mark.asyncio
    async def test_get_subscription_by_stripe_id(self):
        db = AsyncMock()
        mock_sub = MagicMock()
        db.execute.return_value = _mock_result(mock_sub)
        result = await get_subscription_by_stripe_id(db, "sub_test")
        assert result == mock_sub

    @pytest.mark.asyncio
    async def test_get_customer_by_stripe_id(self):
        db = AsyncMock()
        db.execute.return_value = _mock_result(None)
        result = await get_customer_by_stripe_id(db, "cus_test")
        assert result is None


class TestHandleCustomerCreated:
    @pytest.mark.asyncio
    async def test_new_customer(self):
        db = AsyncMock()
        db.execute.return_value = _mock_result(None)  # Not existing
        db.add = MagicMock()

        event = {
            "id": "evt_test",
            "data": {
                "object": {
                    "id": "cus_new",
                    "email": "new@example.com",
                    "name": "New",
                    "metadata": {"saas_id": "saas-1", "external_id": "ext-1"},
                }
            },
        }

        await handle_customer_created(event, db)
        db.add.assert_called_once()

    @pytest.mark.asyncio
    async def test_existing_customer(self):
        db = AsyncMock()
        existing = MagicMock()
        existing.deleted_at = None
        db.execute.return_value = _mock_result(existing)

        event = {
            "id": "evt_test",
            "data": {
                "object": {
                    "id": "cus_existing",
                    "email": "x@x.com",
                    "metadata": {},
                }
            },
        }

        await handle_customer_created(event, db)
        db.add.assert_not_called()

    @pytest.mark.asyncio
    async def test_restore_soft_deleted(self):
        db = AsyncMock()
        existing = MagicMock()
        existing.deleted_at = datetime.now(UTC)
        existing.email = "old@example.com"
        existing.name = "Old"
        db.execute.return_value = _mock_result(existing)

        event = {
            "id": "evt_test",
            "data": {
                "object": {
                    "id": "cus_restored",
                    "email": "new@example.com",
                    "name": "New Name",
                    "metadata": {},
                }
            },
        }

        await handle_customer_created(event, db)
        assert existing.deleted_at is None
        assert existing.email == "new@example.com"
        assert existing.name == "New Name"

    @pytest.mark.asyncio
    async def test_missing_metadata(self):
        db = AsyncMock()
        db.execute.return_value = _mock_result(None)
        db.add = MagicMock()

        event = {
            "id": "evt_test",
            "data": {
                "object": {
                    "id": "cus_no_meta",
                    "email": "x@x.com",
                    "metadata": {},  # Missing saas_id and external_id
                }
            },
        }

        await handle_customer_created(event, db)
        db.add.assert_not_called()


class TestHandleCustomerDeleted:
    @pytest.mark.asyncio
    async def test_soft_delete(self):
        db = AsyncMock()
        customer = MagicMock()
        customer.deleted_at = None
        customer.email = "x@x.com"
        db.execute.return_value = _mock_result(customer)

        event = {"id": "evt_test", "data": {"object": {"id": "cus_del"}}}

        await handle_customer_deleted(event, db)
        assert customer.deleted_at is not None

    @pytest.mark.asyncio
    async def test_not_found(self):
        db = AsyncMock()
        db.execute.return_value = _mock_result(None)

        event = {"id": "evt_test", "data": {"object": {"id": "cus_missing"}}}

        await handle_customer_deleted(event, db)
        # No error

    @pytest.mark.asyncio
    async def test_already_deleted(self):
        db = AsyncMock()
        customer = MagicMock()
        customer.deleted_at = datetime.now(UTC)
        db.execute.return_value = _mock_result(customer)

        event = {"id": "evt_test", "data": {"object": {"id": "cus_del"}}}

        await handle_customer_deleted(event, db)
        # Should not update deleted_at again (stays as-is)


class TestHandleCustomerUpdated:
    @pytest.mark.asyncio
    async def test_update_email_and_name(self):
        db = AsyncMock()
        customer = MagicMock()
        db.execute.return_value = _mock_result(customer)

        event = {
            "id": "evt_test",
            "data": {
                "object": {
                    "id": "cus_upd",
                    "email": "new@example.com",
                    "name": "New Name",
                }
            },
        }

        await handle_customer_updated(event, db)
        assert customer.email == "new@example.com"
        assert customer.name == "New Name"

    @pytest.mark.asyncio
    async def test_not_found(self):
        db = AsyncMock()
        db.execute.return_value = _mock_result(None)

        event = {"id": "evt_test", "data": {"object": {"id": "cus_missing"}}}

        await handle_customer_updated(event, db)

    @pytest.mark.asyncio
    async def test_no_email_or_name(self):
        db = AsyncMock()
        customer = MagicMock()
        customer.email = "old@example.com"
        customer.name = "Old Name"
        db.execute.return_value = _mock_result(customer)

        event = {"id": "evt_test", "data": {"object": {"id": "cus_upd"}}}  # No email/name

        await handle_customer_updated(event, db)
        assert customer.email == "old@example.com"
        assert customer.name == "Old Name"


class TestHandleCheckoutSessionCompleted:
    @pytest.mark.asyncio
    async def test_success(self):
        db = AsyncMock()
        customer = MagicMock()
        customer.saas_app_id = "saas-1"
        customer.id = str(uuid4())
        db.add = MagicMock()

        # 1: customer lookup, 2: subscription lookup (not exists), 3: price lookup
        price = MagicMock()
        price.id = str(uuid4())

        db.execute.side_effect = [
            _mock_result(customer),  # get_customer_by_stripe_id
            _mock_result(None),  # get_subscription_by_stripe_id
            _mock_result(price),  # price lookup
        ]

        event = {
            "id": "evt_test",
            "data": {
                "object": {
                    "id": "cs_test",
                    "metadata": {"saas_id": "saas-1"},
                    "customer": "cus_test",
                    "subscription": "sub_test",
                }
            },
        }

        with patch("billing.routes.webhooks.stripe.Subscription.retrieve") as mock_retrieve:
            mock_stripe_sub = {"items": {"data": [{"price": {"id": "price_stripe"}}]}}
            mock_retrieve.return_value = mock_stripe_sub
            with patch(
                "billing.routes.webhooks.notify_subscription_created", new_callable=AsyncMock
            ):
                await handle_checkout_session_completed(event, db)

        db.add.assert_called_once()

    @pytest.mark.asyncio
    async def test_no_saas_id(self):
        db = AsyncMock()
        event = {
            "id": "evt_test",
            "data": {
                "object": {
                    "id": "cs_test",
                    "metadata": {},
                }
            },
        }

        await handle_checkout_session_completed(event, db)
        db.add.assert_not_called()

    @pytest.mark.asyncio
    async def test_no_subscription(self):
        db = AsyncMock()
        event = {
            "id": "evt_test",
            "data": {
                "object": {
                    "id": "cs_test",
                    "metadata": {"saas_id": "saas-1"},
                    "customer": "cus_test",
                    "subscription": None,
                }
            },
        }

        await handle_checkout_session_completed(event, db)
        db.add.assert_not_called()

    @pytest.mark.asyncio
    async def test_customer_not_found(self):
        db = AsyncMock()
        db.execute.return_value = _mock_result(None)

        event = {
            "id": "evt_test",
            "data": {
                "object": {
                    "id": "cs_test",
                    "metadata": {"saas_id": "saas-1"},
                    "customer": "cus_missing",
                    "subscription": "sub_test",
                }
            },
        }

        await handle_checkout_session_completed(event, db)
        db.add.assert_not_called()

    @pytest.mark.asyncio
    async def test_subscription_already_exists(self):
        db = AsyncMock()
        customer = MagicMock()
        customer.saas_app_id = "saas-1"
        existing_sub = MagicMock()
        db.execute.side_effect = [
            _mock_result(customer),
            _mock_result(existing_sub),  # Already exists
        ]

        event = {
            "id": "evt_test",
            "data": {
                "object": {
                    "id": "cs_test",
                    "metadata": {"saas_id": "saas-1"},
                    "customer": "cus_test",
                    "subscription": "sub_existing",
                }
            },
        }

        await handle_checkout_session_completed(event, db)
        db.add.assert_not_called()

    @pytest.mark.asyncio
    async def test_stripe_sub_no_items(self):
        """Stripe subscription with no items data -> price_id stays None."""
        db = AsyncMock()
        customer = MagicMock()
        customer.saas_app_id = "saas-1"
        customer.id = str(uuid4())
        db.add = MagicMock()

        db.execute.side_effect = [
            _mock_result(customer),
            _mock_result(None),  # subscription not found
        ]

        event = {
            "id": "evt_test",
            "data": {
                "object": {
                    "id": "cs_test",
                    "metadata": {"saas_id": "saas-1"},
                    "customer": "cus_test",
                    "subscription": "sub_test",
                }
            },
        }

        with patch("billing.routes.webhooks.stripe.Subscription.retrieve") as mock_retrieve:
            mock_retrieve.return_value = {"items": {"data": []}}
            with patch(
                "billing.routes.webhooks.notify_subscription_created", new_callable=AsyncMock
            ):
                await handle_checkout_session_completed(event, db)

        db.add.assert_called_once()

    @pytest.mark.asyncio
    async def test_stripe_sub_price_not_found(self):
        """Stripe subscription has items but price not in our DB."""
        db = AsyncMock()
        customer = MagicMock()
        customer.saas_app_id = "saas-1"
        customer.id = str(uuid4())
        db.add = MagicMock()

        db.execute.side_effect = [
            _mock_result(customer),
            _mock_result(None),  # subscription not found
            _mock_result(None),  # price not found in DB
        ]

        event = {
            "id": "evt_test",
            "data": {
                "object": {
                    "id": "cs_test",
                    "metadata": {"saas_id": "saas-1"},
                    "customer": "cus_test",
                    "subscription": "sub_test",
                }
            },
        }

        with patch("billing.routes.webhooks.stripe.Subscription.retrieve") as mock_retrieve:
            mock_retrieve.return_value = {"items": {"data": [{"price": {"id": "price_unknown"}}]}}
            with patch(
                "billing.routes.webhooks.notify_subscription_created", new_callable=AsyncMock
            ):
                await handle_checkout_session_completed(event, db)

        db.add.assert_called_once()

    @pytest.mark.asyncio
    async def test_price_lookup_exception(self):
        db = AsyncMock()
        customer = MagicMock()
        customer.saas_app_id = "saas-1"
        customer.id = str(uuid4())
        db.add = MagicMock()

        db.execute.side_effect = [
            _mock_result(customer),
            _mock_result(None),
        ]

        event = {
            "id": "evt_test",
            "data": {
                "object": {
                    "id": "cs_test",
                    "metadata": {"saas_id": "saas-1"},
                    "customer": "cus_test",
                    "subscription": "sub_test",
                }
            },
        }

        with (
            patch(
                "billing.routes.webhooks.stripe.Subscription.retrieve",
                side_effect=Exception("error"),
            ),
            patch("billing.routes.webhooks.notify_subscription_created", new_callable=AsyncMock),
        ):
            await handle_checkout_session_completed(event, db)

        db.add.assert_called_once()


class TestHandleInvoicePaid:
    @pytest.mark.asyncio
    async def test_reactivate_past_due(self):
        db = AsyncMock()
        sub = MagicMock()
        sub.status = SubscriptionStatus.PAST_DUE
        db.execute.return_value = _mock_result(sub)

        event = {"id": "evt_test", "data": {"object": {"subscription": "sub_test"}}}

        with patch("billing.routes.webhooks.notify_subscription_updated", new_callable=AsyncMock):
            await handle_invoice_paid(event, db)

        assert sub.status == SubscriptionStatus.ACTIVE

    @pytest.mark.asyncio
    async def test_reactivate_unpaid(self):
        db = AsyncMock()
        sub = MagicMock()
        sub.status = SubscriptionStatus.UNPAID
        db.execute.return_value = _mock_result(sub)

        event = {"id": "evt_test", "data": {"object": {"subscription": "sub_test"}}}

        with patch("billing.routes.webhooks.notify_subscription_updated", new_callable=AsyncMock):
            await handle_invoice_paid(event, db)

        assert sub.status == SubscriptionStatus.ACTIVE

    @pytest.mark.asyncio
    async def test_no_subscription_id(self):
        db = AsyncMock()
        event = {"id": "evt_test", "data": {"object": {"subscription": None}}}
        await handle_invoice_paid(event, db)
        db.execute.assert_not_called()

    @pytest.mark.asyncio
    async def test_not_found(self):
        db = AsyncMock()
        db.execute.return_value = _mock_result(None)
        event = {"id": "evt_test", "data": {"object": {"subscription": "sub_missing"}}}
        await handle_invoice_paid(event, db)

    @pytest.mark.asyncio
    async def test_already_active(self):
        db = AsyncMock()
        sub = MagicMock()
        sub.status = SubscriptionStatus.ACTIVE
        db.execute.return_value = _mock_result(sub)
        event = {"id": "evt_test", "data": {"object": {"subscription": "sub_test"}}}
        await handle_invoice_paid(event, db)
        assert sub.status == SubscriptionStatus.ACTIVE  # Unchanged


class TestHandleInvoicePaymentFailed:
    @pytest.mark.asyncio
    async def test_mark_past_due(self):
        db = AsyncMock()
        sub = MagicMock()
        sub.status = SubscriptionStatus.ACTIVE
        db.execute.return_value = _mock_result(sub)

        event = {"id": "evt_test", "data": {"object": {"subscription": "sub_test"}}}

        with patch("billing.routes.webhooks.notify_subscription_updated", new_callable=AsyncMock):
            await handle_invoice_payment_failed(event, db)

        assert sub.status == SubscriptionStatus.PAST_DUE

    @pytest.mark.asyncio
    async def test_no_subscription_id(self):
        db = AsyncMock()
        event = {"id": "evt_test", "data": {"object": {"subscription": None}}}
        await handle_invoice_payment_failed(event, db)
        db.execute.assert_not_called()

    @pytest.mark.asyncio
    async def test_not_found(self):
        db = AsyncMock()
        db.execute.return_value = _mock_result(None)
        event = {"id": "evt_test", "data": {"object": {"subscription": "sub_missing"}}}
        await handle_invoice_payment_failed(event, db)


class TestHandleSubscriptionUpdated:
    @pytest.mark.asyncio
    async def test_full_update(self):
        db = AsyncMock()
        sub = MagicMock()
        db.execute.side_effect = [
            _mock_result(sub),  # subscription lookup
            _mock_result(MagicMock(id="price-1")),  # price lookup
        ]

        event = {
            "id": "evt_test",
            "data": {
                "object": {
                    "id": "sub_test",
                    "status": "active",
                    "cancel_at_period_end": False,
                    "current_period_start": 1704067200,
                    "current_period_end": 1706745600,
                    "canceled_at": 1704067200,
                    "items": {"data": [{"id": "si_item1", "price": {"id": "price_stripe"}}]},
                }
            },
        }

        with patch("billing.routes.webhooks.notify_subscription_updated", new_callable=AsyncMock):
            await handle_subscription_updated(event, db)

        assert sub.status == SubscriptionStatus.ACTIVE

    @pytest.mark.asyncio
    async def test_update_items_no_price_id(self):
        """Subscription updated with items but no price id in item."""
        db = AsyncMock()
        sub = MagicMock()
        db.execute.return_value = _mock_result(sub)

        event = {
            "id": "evt_test",
            "data": {
                "object": {
                    "id": "sub_test",
                    "status": "active",
                    "cancel_at_period_end": False,
                    "current_period_start": 1704067200,
                    "current_period_end": 1706745600,
                    "items": {"data": [{"id": "si_item1", "price": {}}]},  # No "id" in price
                }
            },
        }

        with patch("billing.routes.webhooks.notify_subscription_updated", new_callable=AsyncMock):
            await handle_subscription_updated(event, db)

    @pytest.mark.asyncio
    async def test_update_items_price_not_found_in_db(self):
        """Subscription updated with items and price, but price not in our DB."""
        db = AsyncMock()
        sub = MagicMock()
        db.execute.side_effect = [
            _mock_result(sub),  # subscription lookup
            _mock_result(None),  # price lookup -> not found
        ]

        event = {
            "id": "evt_test",
            "data": {
                "object": {
                    "id": "sub_test",
                    "status": "active",
                    "cancel_at_period_end": False,
                    "current_period_start": 1704067200,
                    "current_period_end": 1706745600,
                    "items": {"data": [{"id": "si_item1", "price": {"id": "price_unknown"}}]},
                }
            },
        }

        with patch("billing.routes.webhooks.notify_subscription_updated", new_callable=AsyncMock):
            await handle_subscription_updated(event, db)
        # price_id should NOT be updated since price wasn't found

    @pytest.mark.asyncio
    async def test_update_no_items(self):
        db = AsyncMock()
        sub = MagicMock()
        db.execute.return_value = _mock_result(sub)

        event = {
            "id": "evt_test",
            "data": {
                "object": {
                    "id": "sub_test",
                    "status": "active",
                    "cancel_at_period_end": False,
                }
            },
        }

        with patch("billing.routes.webhooks.notify_subscription_updated", new_callable=AsyncMock):
            await handle_subscription_updated(event, db)

    @pytest.mark.asyncio
    async def test_not_found(self):
        db = AsyncMock()
        db.execute.return_value = _mock_result(None)

        event = {"id": "evt_test", "data": {"object": {"id": "sub_missing", "status": "active"}}}
        await handle_subscription_updated(event, db)


class TestHandleSubscriptionDeleted:
    @pytest.mark.asyncio
    async def test_delete(self):
        db = AsyncMock()
        sub = MagicMock()
        db.execute.return_value = _mock_result(sub)

        event = {"id": "evt_test", "data": {"object": {"id": "sub_del"}}}

        with patch("billing.routes.webhooks.notify_subscription_deleted", new_callable=AsyncMock):
            await handle_subscription_deleted(event, db)

        assert sub.status == SubscriptionStatus.CANCELED

    @pytest.mark.asyncio
    async def test_not_found(self):
        db = AsyncMock()
        db.execute.return_value = _mock_result(None)
        event = {"id": "evt_test", "data": {"object": {"id": "sub_missing"}}}
        await handle_subscription_deleted(event, db)


class TestWebhookHardening:
    """Isolation between SaaS applications and the metadata of stored subscriptions."""

    @staticmethod
    def _checkout_event(saas_id: str = "saas-1") -> dict:
        return {
            "id": "evt_checkout",
            "data": {
                "object": {
                    "id": "cs_test",
                    "metadata": {"saas_id": saas_id},
                    "customer": "cus_test",
                    "subscription": "sub_test",
                }
            },
        }

    @pytest.mark.asyncio
    async def test_subscription_keeps_the_checkout_session_id_in_extra_data(self):
        """Regression: the session id used to be passed as ``metadata`` and was lost."""
        db = AsyncMock()
        db.add = MagicMock()
        customer = MagicMock(id=str(uuid4()), saas_app_id="saas-1")
        db.execute.side_effect = [
            _mock_result(customer),
            _mock_result(None),
            _mock_result(MagicMock(id=str(uuid4()))),
        ]

        with (
            patch("billing.routes.webhooks.stripe.Subscription.retrieve") as mock_retrieve,
            patch("billing.routes.webhooks.notify_subscription_created", new_callable=AsyncMock),
        ):
            mock_retrieve.return_value = {"items": {"data": [{"price": {"id": "price_stripe"}}]}}
            await handle_checkout_session_completed(self._checkout_event(), db)

        created = db.add.call_args[0][0]
        assert created.extra_data == {"checkout_session_id": "cs_test"}

    @pytest.mark.asyncio
    async def test_checkout_of_another_saas_is_ignored(self):
        """A session tagged for SaaS B cannot create a subscription for a customer of SaaS A."""
        db = AsyncMock()
        db.add = MagicMock()
        db.execute.side_effect = [_mock_result(MagicMock(saas_app_id="saas-a"))]

        with patch(
            "billing.routes.webhooks.notify_subscription_created", new_callable=AsyncMock
        ) as notify:
            await handle_checkout_session_completed(self._checkout_event("saas-b"), db)

        db.add.assert_not_called()
        notify.assert_not_called()

    @pytest.mark.asyncio
    async def test_notification_carries_the_stripe_event_id(self):
        db = AsyncMock()
        db.add = MagicMock()
        customer = MagicMock(id=str(uuid4()), saas_app_id="saas-1")
        db.execute.side_effect = [
            _mock_result(customer),
            _mock_result(None),
            _mock_result(MagicMock(id=str(uuid4()))),
        ]

        with (
            patch("billing.routes.webhooks.stripe.Subscription.retrieve") as mock_retrieve,
            patch(
                "billing.routes.webhooks.notify_subscription_created", new_callable=AsyncMock
            ) as notify,
        ):
            mock_retrieve.return_value = {"items": {"data": [{"price": {"id": "price_stripe"}}]}}
            await handle_checkout_session_completed(self._checkout_event(), db)

        assert notify.call_args[0][2] == "evt_checkout"

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("handler", "notifier", "event_type"),
        [
            (handle_invoice_paid, "notify_subscription_updated", "invoice"),
            (handle_invoice_payment_failed, "notify_subscription_updated", "invoice"),
            (handle_subscription_updated, "notify_subscription_updated", "subscription"),
            (handle_subscription_deleted, "notify_subscription_deleted", "subscription"),
        ],
    )
    async def test_every_notification_carries_the_stripe_event_id(
        self, handler, notifier, event_type
    ):
        db = AsyncMock()
        sub = MagicMock(status=SubscriptionStatus.PAST_DUE)
        db.execute.return_value = _mock_result(sub)
        obj = (
            {"subscription": "sub_test"}
            if event_type == "invoice"
            else {"id": "sub_test", "status": "active"}
        )
        event = {"id": "evt_42", "data": {"object": obj}}

        with patch(f"billing.routes.webhooks.{notifier}", new_callable=AsyncMock) as notify:
            await handler(event, db)

        assert notify.call_args[0][2] == "evt_42"

    @pytest.mark.asyncio
    async def test_customer_created_for_an_unknown_saas_is_skipped(self):
        db = AsyncMock()
        db.add = MagicMock()
        unknown = MagicMock()
        unknown.first.return_value = None
        db.execute.side_effect = [_mock_result(None), unknown]
        event = {
            "id": "evt_test",
            "data": {
                "object": {
                    "id": "cus_new",
                    "email": "new@example.com",
                    "metadata": {"saas_id": "ghost", "external_id": "ext-1"},
                }
            },
        }

        await handle_customer_created(event, db)

        db.add.assert_not_called()

    @pytest.mark.asyncio
    async def test_customer_created_for_a_known_saas_is_stored(self):
        db = AsyncMock()
        db.add = MagicMock()
        known = MagicMock()
        known.first.return_value = ("saas-1",)
        db.execute.side_effect = [_mock_result(None), known]
        event = {
            "id": "evt_test",
            "data": {
                "object": {
                    "id": "cus_new",
                    "email": "new@example.com",
                    "metadata": {"saas_id": "saas-1", "external_id": "ext-1"},
                }
            },
        }

        await handle_customer_created(event, db)

        assert db.add.call_args[0][0].saas_app_id == "saas-1"

    @pytest.mark.asyncio
    async def test_period_is_read_from_the_subscription_item(self):
        """Recent Stripe API versions only carry the billing period on the item."""
        db = AsyncMock()
        sub = MagicMock()
        db.execute.side_effect = [_mock_result(sub), _mock_result(None)]
        event = {
            "id": "evt_test",
            "data": {
                "object": {
                    "id": "sub_test",
                    "status": "active",
                    "items": {
                        "data": [
                            {
                                "id": "si_1",
                                "current_period_start": 1704067200,
                                "current_period_end": 1706745600,
                                "price": {"id": "price_stripe"},
                            }
                        ]
                    },
                }
            },
        }

        with patch("billing.routes.webhooks.notify_subscription_updated", new_callable=AsyncMock):
            await handle_subscription_updated(event, db)

        assert sub.current_period_start == datetime(2024, 1, 1, tzinfo=UTC)
        assert sub.current_period_end == datetime(2024, 2, 1, tzinfo=UTC)


class TestStripeWebhookRoute:
    """Tests for POST /webhooks/stripe."""

    @pytest.mark.asyncio
    @patch("billing.routes.webhooks.async_session_factory")
    @patch("billing.routes.webhooks.stripe.Webhook.construct_event")
    @patch("billing.routes.webhooks.settings")
    async def test_success_unhandled_event(
        self, mock_settings, mock_construct, mock_factory, client
    ):
        mock_settings.stripe_webhook_secret = "whsec_test"
        mock_settings.stripe_webhook_required_scope = ""
        mock_construct.return_value = {"type": "unknown.event", "id": "evt_test"}

        mock_session = AsyncMock()
        mock_cm = AsyncMock()
        mock_cm.__aenter__.return_value = mock_session
        mock_cm.__aexit__.return_value = False
        mock_factory.return_value = mock_cm

        response = await client.post(
            "/webhooks/stripe", content=b"payload", headers={"Stripe-Signature": "sig"}
        )
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}

    @pytest.mark.asyncio
    @patch("billing.routes.webhooks.settings")
    async def test_no_webhook_secret(self, mock_settings, client):
        mock_settings.stripe_webhook_secret = ""
        mock_settings.stripe_webhook_required_scope = ""

        response = await client.post(
            "/webhooks/stripe", content=b"payload", headers={"Stripe-Signature": "sig"}
        )
        assert response.status_code == 500

    @pytest.mark.asyncio
    @patch("billing.routes.webhooks.stripe.Webhook.construct_event")
    @patch("billing.routes.webhooks.settings")
    async def test_invalid_signature(self, mock_settings, mock_construct, client):
        import stripe as stripe_mod

        mock_settings.stripe_webhook_secret = "whsec_test"
        mock_settings.stripe_webhook_required_scope = ""
        mock_construct.side_effect = stripe_mod.SignatureVerificationError("bad sig", "sig_header")

        response = await client.post(
            "/webhooks/stripe", content=b"payload", headers={"Stripe-Signature": "bad"}
        )
        assert response.status_code == 400

    @pytest.mark.asyncio
    @patch("billing.routes.webhooks.stripe.Webhook.construct_event")
    @patch("billing.routes.webhooks.settings")
    async def test_invalid_payload(self, mock_settings, mock_construct, client):
        mock_settings.stripe_webhook_secret = "whsec_test"
        mock_settings.stripe_webhook_required_scope = ""
        mock_construct.side_effect = ValueError("bad payload")

        response = await client.post(
            "/webhooks/stripe", content=b"bad", headers={"Stripe-Signature": "sig"}
        )
        assert response.status_code == 400

    @pytest.mark.asyncio
    @patch("billing.routes.webhooks.async_session_factory")
    @patch("billing.routes.webhooks.stripe.Webhook.construct_event")
    @patch("billing.routes.webhooks.settings")
    async def test_handler_error(self, mock_settings, mock_construct, mock_factory, client):
        mock_settings.stripe_webhook_secret = "whsec_test"
        mock_settings.stripe_webhook_required_scope = ""
        mock_construct.return_value = {
            "type": "customer.created",
            "id": "evt_test",
            "data": {
                "object": {"id": "cus_test", "metadata": {"saas_id": "s", "external_id": "e"}}
            },
        }

        mock_session = AsyncMock()
        mock_session.execute.side_effect = Exception("DB error")
        mock_cm = AsyncMock()
        mock_cm.__aenter__.return_value = mock_session
        mock_cm.__aexit__.return_value = False
        mock_factory.return_value = mock_cm

        response = await client.post(
            "/webhooks/stripe", content=b"payload", headers={"Stripe-Signature": "sig"}
        )
        assert response.status_code == 500

    @pytest.mark.asyncio
    @patch("billing.routes.webhooks.async_session_factory")
    @patch("billing.routes.webhooks.stripe.Webhook.construct_event")
    @patch("billing.routes.webhooks.settings")
    async def test_all_event_types_dispatch(
        self, mock_settings, mock_construct, mock_factory, client
    ):
        """Test that all known event types are dispatched without error."""
        mock_settings.stripe_webhook_secret = "whsec_test"
        mock_settings.stripe_webhook_required_scope = ""

        mock_session = AsyncMock()
        mock_session.execute.return_value = _mock_result(None)
        mock_cm = AsyncMock()
        mock_cm.__aenter__.return_value = mock_session
        mock_cm.__aexit__.return_value = False
        mock_factory.return_value = mock_cm

        event_types = [
            "checkout.session.completed",
            "invoice.paid",
            "invoice.payment_failed",
            "customer.subscription.updated",
            "customer.subscription.deleted",
            "customer.created",
            "customer.updated",
            "customer.deleted",
        ]

        for event_type in event_types:
            mock_factory.reset_mock()
            mock_session.execute.return_value = _mock_result(None)
            mock_session.execute.side_effect = None
            mock_construct.return_value = {
                "type": event_type,
                "id": "evt_test",
                "data": {
                    "object": {
                        "id": "obj_test",
                        "metadata": {},
                        "subscription": None,
                    }
                },
            }

            response = await client.post(
                "/webhooks/stripe", content=b"payload", headers={"Stripe-Signature": "sig"}
            )
            assert response.status_code == 200, f"Failed for event type: {event_type}"


class TestStripeWebhookAuthentication:
    """The signature is the authentication; a bearer token is optional by configuration."""

    def _session_factory(self, mock_factory):
        mock_session = AsyncMock()
        mock_cm = AsyncMock()
        mock_cm.__aenter__.return_value = mock_session
        mock_cm.__aexit__.return_value = False
        mock_factory.return_value = mock_cm

    @pytest.mark.asyncio
    @patch("billing.routes.webhooks.async_session_factory")
    @patch("billing.routes.webhooks.stripe.Webhook.construct_event")
    async def test_works_without_any_token(self, mock_construct, mock_factory, client, monkeypatch):
        """Stripe cannot send a bearer token: a valid signature is enough."""
        monkeypatch.setattr(settings, "stripe_webhook_secret", "whsec_test")
        monkeypatch.setattr(settings, "stripe_webhook_required_scope", "")
        mock_construct.return_value = {"type": "unknown.event", "id": "evt_test"}
        self._session_factory(mock_factory)

        response = await client.post(
            "/webhooks/stripe", content=b"payload", headers={"Stripe-Signature": "sig"}
        )

        assert response.status_code == 200
        assert mock_construct.call_args[0][2] == "whsec_test"

    @pytest.mark.asyncio
    @patch("billing.routes.webhooks.async_session_factory")
    @patch("billing.routes.webhooks.stripe.Webhook.construct_event")
    async def test_a_token_sent_by_the_proxy_is_accepted_and_ignored(
        self, mock_construct, mock_factory, webhook_client, monkeypatch
    ):
        monkeypatch.setattr(settings, "stripe_webhook_secret", "whsec_test")
        monkeypatch.setattr(settings, "stripe_webhook_required_scope", "")
        mock_construct.return_value = {"type": "unknown.event", "id": "evt_test"}
        self._session_factory(mock_factory)

        response = await webhook_client.post(
            "/webhooks/stripe", content=b"payload", headers={"Stripe-Signature": "sig"}
        )

        assert response.status_code == 200

    @pytest.mark.asyncio
    @patch("billing.routes.webhooks.stripe.Webhook.construct_event")
    async def test_the_signature_is_still_required(
        self, mock_construct, webhook_client, monkeypatch
    ):
        """Having a token does not replace the signature."""
        import stripe as stripe_mod

        monkeypatch.setattr(settings, "stripe_webhook_secret", "whsec_test")
        monkeypatch.setattr(settings, "stripe_webhook_required_scope", "")
        mock_construct.side_effect = stripe_mod.SignatureVerificationError("bad", "sig")

        response = await webhook_client.post(
            "/webhooks/stripe", content=b"payload", headers={"Stripe-Signature": "forged"}
        )

        assert response.status_code == 400

    @pytest.mark.asyncio
    async def test_required_scope_rejects_anonymous_requests(self, client, monkeypatch):
        monkeypatch.setattr(settings, "stripe_webhook_required_scope", "billing:webhooks")

        response = await client.post(
            "/webhooks/stripe", content=b"payload", headers={"Stripe-Signature": "sig"}
        )

        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_required_scope_rejects_a_token_without_it(self, auth_client, monkeypatch):
        monkeypatch.setattr(settings, "stripe_webhook_required_scope", "billing:webhooks")

        response = await auth_client.post(
            "/webhooks/stripe", content=b"payload", headers={"Stripe-Signature": "sig"}
        )

        assert response.status_code == 403

    @pytest.mark.asyncio
    @patch("billing.routes.webhooks.async_session_factory")
    @patch("billing.routes.webhooks.stripe.Webhook.construct_event")
    async def test_required_scope_accepts_a_token_with_it(
        self, mock_construct, mock_factory, webhook_client, monkeypatch
    ):
        monkeypatch.setattr(settings, "stripe_webhook_secret", "whsec_test")
        monkeypatch.setattr(settings, "stripe_webhook_required_scope", "billing:webhooks")
        mock_construct.return_value = {"type": "unknown.event", "id": "evt_test"}
        self._session_factory(mock_factory)

        response = await webhook_client.post(
            "/webhooks/stripe", content=b"payload", headers={"Stripe-Signature": "sig"}
        )

        assert response.status_code == 200

    def test_no_scope_is_required_by_default(self):
        from billing.config import Settings

        assert Settings(_env_file=None).stripe_webhook_required_scope == ""
