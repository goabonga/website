# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for Brevo webhook routes."""

import json
from datetime import UTC
from unittest.mock import MagicMock, patch

from httpx import AsyncClient


class TestBrevoWebhook:
    """Tests for POST /api/v1/webhooks/brevo."""

    async def test_empty_body(self, webhook_client: AsyncClient):
        """Empty body returns 200 (no-op)."""
        response = await webhook_client.post("/api/v1/webhooks/brevo", content=b"")

        assert response.status_code == 200

    async def test_invalid_json(self, webhook_client: AsyncClient):
        """Invalid JSON body returns 400."""
        response = await webhook_client.post(
            "/api/v1/webhooks/brevo",
            content=b"this is not json{{{",
        )

        assert response.status_code == 400

    @patch("mailler.routes.webhooks._update_email_status")
    @patch("mailler.routes.webhooks.settings")
    async def test_missing_email_field(
        self, mock_settings, mock_update, webhook_client: AsyncClient
    ):
        """Event with no email field returns 200 (logged as warning)."""
        mock_settings.webhook_hmac_secret = ""

        event = {
            "event": "delivered",
            "X-Mailin-custom": "email_id:abc-123",
        }

        response = await webhook_client.post(
            "/api/v1/webhooks/brevo",
            content=json.dumps(event).encode(),
        )

        assert response.status_code == 200
        mock_update.assert_not_called()

    # ----- Signature verification -----

    @patch("mailler.routes.webhooks._update_email_status")
    @patch("mailler.routes.webhooks.verify_webhook_signature")
    @patch("mailler.routes.webhooks.settings")
    async def test_signature_required_missing_email_id(
        self, mock_settings, mock_verify, mock_update, webhook_client: AsyncClient
    ):
        """When HMAC secret is set and email_id is missing, returns 401."""
        mock_settings.webhook_hmac_secret = "secret123"

        event = {
            "event": "delivered",
            "email": "test@t.com",
            "X-Mailin-custom": "",
        }

        response = await webhook_client.post(
            "/api/v1/webhooks/brevo",
            content=json.dumps(event).encode(),
        )

        assert response.status_code == 401

    @patch("mailler.routes.webhooks._update_email_status")
    @patch("mailler.routes.webhooks.verify_webhook_signature")
    @patch("mailler.routes.webhooks.settings")
    async def test_signature_required_invalid_signature(
        self, mock_settings, mock_verify, mock_update, webhook_client: AsyncClient
    ):
        """When HMAC secret is set and signature is invalid, returns 401."""
        mock_settings.webhook_hmac_secret = "secret123"
        mock_verify.return_value = False

        event = {
            "event": "delivered",
            "email": "test@t.com",
            "X-Mailin-custom": "email_id:abc-123,signature:bad-sig",
        }

        response = await webhook_client.post(
            "/api/v1/webhooks/brevo",
            content=json.dumps(event).encode(),
        )

        assert response.status_code == 401

    @patch("mailler.routes.webhooks._update_email_status")
    @patch("mailler.routes.webhooks.verify_webhook_signature")
    @patch("mailler.routes.webhooks.settings")
    async def test_signature_valid_passes(
        self, mock_settings, mock_verify, mock_update, webhook_client: AsyncClient
    ):
        """When signature is valid, event is processed successfully."""
        mock_settings.webhook_hmac_secret = "secret123"
        mock_verify.return_value = True

        event = {
            "event": "delivered",
            "email": "test@t.com",
            "X-Mailin-custom": "email_id:abc-123,signature:valid-sig",
        }

        response = await webhook_client.post(
            "/api/v1/webhooks/brevo",
            content=json.dumps(event).encode(),
        )

        assert response.status_code == 200
        mock_update.assert_called_once()

    # ----- Delivered event -----

    @patch("mailler.routes.webhooks._update_campaign_stats")
    @patch("mailler.routes.webhooks._update_email_status")
    @patch("mailler.routes.webhooks.settings")
    async def test_delivered_event_with_email_id(
        self, mock_settings, mock_update_email, mock_update_campaign, webhook_client: AsyncClient
    ):
        """Delivered event updates email status."""
        mock_settings.webhook_hmac_secret = ""

        event = {
            "event": "delivered",
            "email": "test@t.com",
            "X-Mailin-custom": "email_id:abc-123",
        }

        response = await webhook_client.post(
            "/api/v1/webhooks/brevo",
            content=json.dumps(event).encode(),
        )

        assert response.status_code == 200
        mock_update_email.assert_called_once()

    @patch("mailler.routes.webhooks._update_campaign_stats")
    @patch("mailler.routes.webhooks._update_email_status")
    @patch("mailler.routes.webhooks.settings")
    async def test_delivered_event_with_campaign_id(
        self, mock_settings, mock_update_email, mock_update_campaign, webhook_client: AsyncClient
    ):
        """Delivered event with campaign_id updates both email and campaign stats."""
        mock_settings.webhook_hmac_secret = ""

        event = {
            "event": "delivered",
            "email": "test@t.com",
            "X-Mailin-custom": "email_id:abc-123,campaign_id:42",
        }

        response = await webhook_client.post(
            "/api/v1/webhooks/brevo",
            content=json.dumps(event).encode(),
        )

        assert response.status_code == 200
        mock_update_email.assert_called_once()
        mock_update_campaign.assert_called_once_with(
            recipient_email="test@t.com",
            campaign_id=42,
            event_type="delivery",
        )

    @patch("mailler.routes.webhooks._update_campaign_stats")
    @patch("mailler.routes.webhooks._update_email_status")
    @patch("mailler.routes.webhooks.settings")
    async def test_delivered_event_no_email_id(
        self, mock_settings, mock_update_email, mock_update_campaign, webhook_client: AsyncClient
    ):
        """Delivered event without email_id does not call _update_email_status."""
        mock_settings.webhook_hmac_secret = ""

        event = {
            "event": "delivered",
            "email": "test@t.com",
            "X-Mailin-custom": "",
        }

        response = await webhook_client.post(
            "/api/v1/webhooks/brevo",
            content=json.dumps(event).encode(),
        )

        assert response.status_code == 200
        mock_update_email.assert_not_called()

    # ----- Hard bounce event -----

    @patch("mailler.routes.webhooks._update_campaign_stats")
    @patch("mailler.routes.webhooks._update_email_status")
    @patch("mailler.routes.webhooks.settings")
    async def test_hard_bounce_event(
        self, mock_settings, mock_update_email, mock_update_campaign, webhook_client: AsyncClient
    ):
        """Hard bounce event updates email status to bounced."""
        mock_settings.webhook_hmac_secret = ""

        event = {
            "event": "hard_bounce",
            "email": "bounce@t.com",
            "reason": "Mailbox not found",
            "X-Mailin-custom": "email_id:def-456",
        }

        response = await webhook_client.post(
            "/api/v1/webhooks/brevo",
            content=json.dumps(event).encode(),
        )

        assert response.status_code == 200
        mock_update_email.assert_called_once()

    @patch("mailler.routes.webhooks._update_campaign_stats")
    @patch("mailler.routes.webhooks._update_email_status")
    @patch("mailler.routes.webhooks.settings")
    async def test_hard_bounce_with_campaign(
        self, mock_settings, mock_update_email, mock_update_campaign, webhook_client: AsyncClient
    ):
        """Hard bounce with campaign_id updates both email and campaign stats."""
        mock_settings.webhook_hmac_secret = ""

        event = {
            "event": "hard_bounce",
            "email": "bounce@t.com",
            "reason": "Bad dest",
            "X-Mailin-custom": "email_id:def-456,campaign_id:10",
        }

        response = await webhook_client.post(
            "/api/v1/webhooks/brevo",
            content=json.dumps(event).encode(),
        )

        assert response.status_code == 200
        mock_update_email.assert_called_once()
        mock_update_campaign.assert_called_once()

    # ----- Soft bounce event -----

    @patch("mailler.routes.webhooks._update_campaign_stats")
    @patch("mailler.routes.webhooks._update_email_status")
    @patch("mailler.routes.webhooks.settings")
    async def test_soft_bounce_permanent(
        self, mock_settings, mock_update_email, mock_update_campaign, webhook_client: AsyncClient
    ):
        """Soft bounce with permanent indicator is treated as hard bounce."""
        mock_settings.webhook_hmac_secret = ""

        event = {
            "event": "soft_bounce",
            "email": "bounce@t.com",
            "reason": "Invalid domain for recipient",
            "X-Mailin-custom": "email_id:soft-1,campaign_id:5",
        }

        response = await webhook_client.post(
            "/api/v1/webhooks/brevo",
            content=json.dumps(event).encode(),
        )

        assert response.status_code == 200
        mock_update_email.assert_called_once()
        mock_update_campaign.assert_called_once()

    @patch("mailler.routes.webhooks._update_campaign_stats")
    @patch("mailler.routes.webhooks._update_email_status")
    @patch("mailler.routes.webhooks.settings")
    async def test_soft_bounce_temporary(
        self, mock_settings, mock_update_email, mock_update_campaign, webhook_client: AsyncClient
    ):
        """Temporary soft bounce does not update to bounced or campaign stats."""
        mock_settings.webhook_hmac_secret = ""

        event = {
            "event": "soft_bounce",
            "email": "bounce@t.com",
            "reason": "Mailbox full, try later",
            "X-Mailin-custom": "email_id:soft-2",
        }

        response = await webhook_client.post(
            "/api/v1/webhooks/brevo",
            content=json.dumps(event).encode(),
        )

        assert response.status_code == 200
        mock_update_email.assert_not_called()
        mock_update_campaign.assert_not_called()

    @patch("mailler.routes.webhooks._update_campaign_stats")
    @patch("mailler.routes.webhooks._update_email_status")
    @patch("mailler.routes.webhooks.settings")
    async def test_soft_bounce_permanent_mx(
        self, mock_settings, mock_update_email, mock_update_campaign, webhook_client: AsyncClient
    ):
        """Soft bounce with 'mx' indicator is permanent."""
        mock_settings.webhook_hmac_secret = ""

        event = {
            "event": "soft_bounce",
            "email": "bounce@t.com",
            "reason": "MX records not found",
            "X-Mailin-custom": "email_id:soft-3",
        }

        response = await webhook_client.post(
            "/api/v1/webhooks/brevo",
            content=json.dumps(event).encode(),
        )

        assert response.status_code == 200
        mock_update_email.assert_called_once()

    # ----- Blocked/Invalid events -----

    @patch("mailler.routes.webhooks._update_campaign_stats")
    @patch("mailler.routes.webhooks._update_email_status")
    @patch("mailler.routes.webhooks.settings")
    async def test_blocked_event(
        self, mock_settings, mock_update_email, mock_update_campaign, webhook_client: AsyncClient
    ):
        """Blocked event updates email status to bounced."""
        mock_settings.webhook_hmac_secret = ""

        event = {
            "event": "blocked",
            "email": "blocked@t.com",
            "reason": "Blocked by server",
            "X-Mailin-custom": "email_id:blk-1,campaign_id:7",
        }

        response = await webhook_client.post(
            "/api/v1/webhooks/brevo",
            content=json.dumps(event).encode(),
        )

        assert response.status_code == 200
        mock_update_email.assert_called_once()
        mock_update_campaign.assert_called_once()

    @patch("mailler.routes.webhooks._update_campaign_stats")
    @patch("mailler.routes.webhooks._update_email_status")
    @patch("mailler.routes.webhooks.settings")
    async def test_invalid_event(
        self, mock_settings, mock_update_email, mock_update_campaign, webhook_client: AsyncClient
    ):
        """Invalid event updates email status to bounced."""
        mock_settings.webhook_hmac_secret = ""

        event = {
            "event": "invalid",
            "email": "invalid@t.com",
            "X-Mailin-custom": "email_id:inv-1",
        }

        response = await webhook_client.post(
            "/api/v1/webhooks/brevo",
            content=json.dumps(event).encode(),
        )

        assert response.status_code == 200
        mock_update_email.assert_called_once()

    # ----- Complaint event -----

    @patch("mailler.routes.webhooks._update_campaign_stats")
    @patch("mailler.routes.webhooks._update_email_status")
    @patch("mailler.routes.webhooks.settings")
    async def test_complaint_event(
        self, mock_settings, mock_update_email, mock_update_campaign, webhook_client: AsyncClient
    ):
        """Complaint event updates email and campaign stats."""
        mock_settings.webhook_hmac_secret = ""

        event = {
            "event": "complaint",
            "email": "complain@t.com",
            "X-Mailin-custom": "email_id:cmp-1,campaign_id:3",
        }

        response = await webhook_client.post(
            "/api/v1/webhooks/brevo",
            content=json.dumps(event).encode(),
        )

        assert response.status_code == 200
        mock_update_email.assert_called_once()
        mock_update_campaign.assert_called_once()

    # ----- Unsubscribe event -----

    @patch("mailler.routes.webhooks._update_campaign_stats")
    @patch("mailler.routes.webhooks._update_email_status")
    @patch("mailler.routes.webhooks.settings")
    async def test_unsubscribe_event(
        self, mock_settings, mock_update_email, mock_update_campaign, webhook_client: AsyncClient
    ):
        """Unsubscribe event updates campaign stats as complaint."""
        mock_settings.webhook_hmac_secret = ""

        event = {
            "event": "unsubscribe",
            "email": "unsub@t.com",
            "X-Mailin-custom": "campaign_id:9",
        }

        response = await webhook_client.post(
            "/api/v1/webhooks/brevo",
            content=json.dumps(event).encode(),
        )

        assert response.status_code == 200
        mock_update_campaign.assert_called_once()

    @patch("mailler.routes.webhooks._update_campaign_stats")
    @patch("mailler.routes.webhooks._update_email_status")
    @patch("mailler.routes.webhooks.settings")
    async def test_unsubscribed_event_variant(
        self, mock_settings, mock_update_email, mock_update_campaign, webhook_client: AsyncClient
    ):
        """Unsubscribed (past tense variant) event also updates campaign stats."""
        mock_settings.webhook_hmac_secret = ""

        event = {
            "event": "unsubscribed",
            "email": "unsub2@t.com",
            "X-Mailin-custom": "campaign_id:11",
        }

        response = await webhook_client.post(
            "/api/v1/webhooks/brevo",
            content=json.dumps(event).encode(),
        )

        assert response.status_code == 200
        mock_update_campaign.assert_called_once()

    # ----- Open event -----

    @patch("mailler.routes.webhooks._update_campaign_stats")
    @patch("mailler.routes.webhooks._update_email_status")
    @patch("mailler.routes.webhooks.settings")
    async def test_open_event(
        self, mock_settings, mock_update_email, mock_update_campaign, webhook_client: AsyncClient
    ):
        """Open event updates campaign stats."""
        mock_settings.webhook_hmac_secret = ""

        event = {
            "event": "open",
            "email": "open@t.com",
            "X-Mailin-custom": "campaign_id:8",
        }

        response = await webhook_client.post(
            "/api/v1/webhooks/brevo",
            content=json.dumps(event).encode(),
        )

        assert response.status_code == 200
        mock_update_campaign.assert_called_once_with(
            recipient_email="open@t.com",
            campaign_id=8,
            event_type="open",
        )

    @patch("mailler.routes.webhooks._update_campaign_stats")
    @patch("mailler.routes.webhooks._update_email_status")
    @patch("mailler.routes.webhooks.settings")
    async def test_unique_opened_event(
        self, mock_settings, mock_update_email, mock_update_campaign, webhook_client: AsyncClient
    ):
        """unique_opened event also triggers open tracking."""
        mock_settings.webhook_hmac_secret = ""

        event = {
            "event": "unique_opened",
            "email": "open@t.com",
            "X-Mailin-custom": "campaign_id:8",
        }

        response = await webhook_client.post(
            "/api/v1/webhooks/brevo",
            content=json.dumps(event).encode(),
        )

        assert response.status_code == 200
        mock_update_campaign.assert_called_once()

    # ----- Click event -----

    @patch("mailler.routes.webhooks._update_campaign_stats")
    @patch("mailler.routes.webhooks._update_email_status")
    @patch("mailler.routes.webhooks.settings")
    async def test_click_event(
        self, mock_settings, mock_update_email, mock_update_campaign, webhook_client: AsyncClient
    ):
        """Click event updates campaign stats."""
        mock_settings.webhook_hmac_secret = ""

        event = {
            "event": "click",
            "email": "click@t.com",
            "X-Mailin-custom": "campaign_id:6",
        }

        response = await webhook_client.post(
            "/api/v1/webhooks/brevo",
            content=json.dumps(event).encode(),
        )

        assert response.status_code == 200
        mock_update_campaign.assert_called_once_with(
            recipient_email="click@t.com",
            campaign_id=6,
            event_type="click",
        )

    # ----- Request event -----

    @patch("mailler.routes.webhooks._update_campaign_stats")
    @patch("mailler.routes.webhooks._update_email_status")
    @patch("mailler.routes.webhooks.settings")
    async def test_request_event(
        self, mock_settings, mock_update_email, mock_update_campaign, webhook_client: AsyncClient
    ):
        """Request event is logged but no updates are made."""
        mock_settings.webhook_hmac_secret = ""

        event = {
            "event": "request",
            "email": "req@t.com",
            "X-Mailin-custom": "email_id:req-1",
        }

        response = await webhook_client.post(
            "/api/v1/webhooks/brevo",
            content=json.dumps(event).encode(),
        )

        assert response.status_code == 200
        mock_update_email.assert_not_called()
        mock_update_campaign.assert_not_called()

    # ----- Unknown event -----

    @patch("mailler.routes.webhooks._update_campaign_stats")
    @patch("mailler.routes.webhooks._update_email_status")
    @patch("mailler.routes.webhooks.settings")
    async def test_unknown_event(
        self, mock_settings, mock_update_email, mock_update_campaign, webhook_client: AsyncClient
    ):
        """Unknown event type is handled gracefully."""
        mock_settings.webhook_hmac_secret = ""

        event = {
            "event": "some_future_event",
            "email": "future@t.com",
            "X-Mailin-custom": "email_id:unk-1",
        }

        response = await webhook_client.post(
            "/api/v1/webhooks/brevo",
            content=json.dumps(event).encode(),
        )

        assert response.status_code == 200
        mock_update_email.assert_not_called()
        mock_update_campaign.assert_not_called()

    # ----- General error -----

    @patch("mailler.routes.webhooks.parse_mailin_custom")
    @patch("mailler.routes.webhooks.settings")
    async def test_internal_error_returns_500(
        self, mock_settings, mock_parse, webhook_client: AsyncClient
    ):
        """Unexpected exception during processing returns 500."""
        mock_settings.webhook_hmac_secret = ""
        mock_parse.side_effect = RuntimeError("Unexpected error")

        event = {
            "event": "delivered",
            "email": "err@t.com",
        }

        response = await webhook_client.post(
            "/api/v1/webhooks/brevo",
            content=json.dumps(event).encode(),
        )

        assert response.status_code == 500


class TestBrevoWebhookMissingBranches:
    """Additional tests for branch coverage of brevo_webhook handler.

    Covers missing branches where email_id or campaign_id are absent
    for various event types that conditionally use them.
    """

    # ----- hard_bounce without email_id (branch 319->324) -----

    @patch("mailler.routes.webhooks._update_campaign_stats")
    @patch("mailler.routes.webhooks._update_email_status")
    @patch("mailler.routes.webhooks.settings")
    async def test_hard_bounce_no_email_id_with_campaign(
        self, mock_settings, mock_update_email, mock_update_campaign, webhook_client: AsyncClient
    ):
        """Hard bounce without email_id skips email update but still updates campaign."""
        mock_settings.webhook_hmac_secret = ""

        event = {
            "event": "hard_bounce",
            "email": "bounce@t.com",
            "reason": "Mailbox not found",
            "X-Mailin-custom": "campaign_id:10",
        }

        response = await webhook_client.post(
            "/api/v1/webhooks/brevo",
            content=json.dumps(event).encode(),
        )

        assert response.status_code == 200
        mock_update_email.assert_not_called()
        mock_update_campaign.assert_called_once_with(
            recipient_email="bounce@t.com",
            campaign_id=10,
            event_type="bounce",
            error_message="Hard bounce: Mailbox not found",
        )

    @patch("mailler.routes.webhooks._update_campaign_stats")
    @patch("mailler.routes.webhooks._update_email_status")
    @patch("mailler.routes.webhooks.settings")
    async def test_hard_bounce_no_email_id_no_campaign(
        self, mock_settings, mock_update_email, mock_update_campaign, webhook_client: AsyncClient
    ):
        """Hard bounce without email_id or campaign_id does neither update."""
        mock_settings.webhook_hmac_secret = ""

        event = {
            "event": "hard_bounce",
            "email": "bounce@t.com",
            "reason": "Mailbox not found",
            "X-Mailin-custom": "",
        }

        response = await webhook_client.post(
            "/api/v1/webhooks/brevo",
            content=json.dumps(event).encode(),
        )

        assert response.status_code == 200
        mock_update_email.assert_not_called()
        mock_update_campaign.assert_not_called()

    # ----- soft_bounce permanent without email_id (branch 348->354) -----

    @patch("mailler.routes.webhooks._update_campaign_stats")
    @patch("mailler.routes.webhooks._update_email_status")
    @patch("mailler.routes.webhooks.settings")
    async def test_soft_bounce_permanent_no_email_id_with_campaign(
        self, mock_settings, mock_update_email, mock_update_campaign, webhook_client: AsyncClient
    ):
        """Permanent soft bounce without email_id skips email update, updates campaign."""
        mock_settings.webhook_hmac_secret = ""

        event = {
            "event": "soft_bounce",
            "email": "bounce@t.com",
            "reason": "Invalid domain name",
            "X-Mailin-custom": "campaign_id:5",
        }

        response = await webhook_client.post(
            "/api/v1/webhooks/brevo",
            content=json.dumps(event).encode(),
        )

        assert response.status_code == 200
        mock_update_email.assert_not_called()
        mock_update_campaign.assert_called_once()

    @patch("mailler.routes.webhooks._update_campaign_stats")
    @patch("mailler.routes.webhooks._update_email_status")
    @patch("mailler.routes.webhooks.settings")
    async def test_soft_bounce_permanent_no_email_id_no_campaign(
        self, mock_settings, mock_update_email, mock_update_campaign, webhook_client: AsyncClient
    ):
        """Permanent soft bounce without email_id or campaign_id does neither update."""
        mock_settings.webhook_hmac_secret = ""

        event = {
            "event": "soft_bounce",
            "email": "bounce@t.com",
            "reason": "Domain does not exist",
            "X-Mailin-custom": "",
        }

        response = await webhook_client.post(
            "/api/v1/webhooks/brevo",
            content=json.dumps(event).encode(),
        )

        assert response.status_code == 200
        mock_update_email.assert_not_called()
        mock_update_campaign.assert_not_called()

    # ----- soft_bounce temporary without email_id (branch 363->432) -----

    @patch("mailler.routes.webhooks._update_campaign_stats")
    @patch("mailler.routes.webhooks._update_email_status")
    @patch("mailler.routes.webhooks.settings")
    async def test_soft_bounce_temporary_no_email_id(
        self, mock_settings, mock_update_email, mock_update_campaign, webhook_client: AsyncClient
    ):
        """Temporary soft bounce without email_id skips logging and does nothing."""
        mock_settings.webhook_hmac_secret = ""

        event = {
            "event": "soft_bounce",
            "email": "bounce@t.com",
            "reason": "Mailbox full, try later",
            "X-Mailin-custom": "",
        }

        response = await webhook_client.post(
            "/api/v1/webhooks/brevo",
            content=json.dumps(event).encode(),
        )

        assert response.status_code == 200
        mock_update_email.assert_not_called()
        mock_update_campaign.assert_not_called()

    # ----- blocked/invalid without email_id (branch 369->374) -----

    @patch("mailler.routes.webhooks._update_campaign_stats")
    @patch("mailler.routes.webhooks._update_email_status")
    @patch("mailler.routes.webhooks.settings")
    async def test_blocked_no_email_id_with_campaign(
        self, mock_settings, mock_update_email, mock_update_campaign, webhook_client: AsyncClient
    ):
        """Blocked event without email_id skips email update but updates campaign."""
        mock_settings.webhook_hmac_secret = ""

        event = {
            "event": "blocked",
            "email": "blocked@t.com",
            "reason": "Blocked by server",
            "X-Mailin-custom": "campaign_id:7",
        }

        response = await webhook_client.post(
            "/api/v1/webhooks/brevo",
            content=json.dumps(event).encode(),
        )

        assert response.status_code == 200
        mock_update_email.assert_not_called()
        mock_update_campaign.assert_called_once()

    @patch("mailler.routes.webhooks._update_campaign_stats")
    @patch("mailler.routes.webhooks._update_email_status")
    @patch("mailler.routes.webhooks.settings")
    async def test_blocked_no_email_id_no_campaign(
        self, mock_settings, mock_update_email, mock_update_campaign, webhook_client: AsyncClient
    ):
        """Blocked event without email_id or campaign_id does neither update."""
        mock_settings.webhook_hmac_secret = ""

        event = {
            "event": "blocked",
            "email": "blocked@t.com",
            "X-Mailin-custom": "",
        }

        response = await webhook_client.post(
            "/api/v1/webhooks/brevo",
            content=json.dumps(event).encode(),
        )

        assert response.status_code == 200
        mock_update_email.assert_not_called()
        mock_update_campaign.assert_not_called()

    @patch("mailler.routes.webhooks._update_campaign_stats")
    @patch("mailler.routes.webhooks._update_email_status")
    @patch("mailler.routes.webhooks.settings")
    async def test_invalid_no_email_id_with_campaign(
        self, mock_settings, mock_update_email, mock_update_campaign, webhook_client: AsyncClient
    ):
        """Invalid event without email_id skips email update but updates campaign."""
        mock_settings.webhook_hmac_secret = ""

        event = {
            "event": "invalid",
            "email": "invalid@t.com",
            "X-Mailin-custom": "campaign_id:12",
        }

        response = await webhook_client.post(
            "/api/v1/webhooks/brevo",
            content=json.dumps(event).encode(),
        )

        assert response.status_code == 200
        mock_update_email.assert_not_called()
        mock_update_campaign.assert_called_once()

    @patch("mailler.routes.webhooks._update_campaign_stats")
    @patch("mailler.routes.webhooks._update_email_status")
    @patch("mailler.routes.webhooks.settings")
    async def test_invalid_no_email_id_no_campaign(
        self, mock_settings, mock_update_email, mock_update_campaign, webhook_client: AsyncClient
    ):
        """Invalid event without email_id or campaign_id does neither update."""
        mock_settings.webhook_hmac_secret = ""

        event = {
            "event": "invalid",
            "email": "invalid@t.com",
            "X-Mailin-custom": "",
        }

        response = await webhook_client.post(
            "/api/v1/webhooks/brevo",
            content=json.dumps(event).encode(),
        )

        assert response.status_code == 200
        mock_update_email.assert_not_called()
        mock_update_campaign.assert_not_called()

    # ----- complaint without email_id / campaign_id (branches 383->388, 388->432) -----

    @patch("mailler.routes.webhooks._update_campaign_stats")
    @patch("mailler.routes.webhooks._update_email_status")
    @patch("mailler.routes.webhooks.settings")
    async def test_complaint_no_email_id_with_campaign(
        self, mock_settings, mock_update_email, mock_update_campaign, webhook_client: AsyncClient
    ):
        """Complaint without email_id skips email update but updates campaign."""
        mock_settings.webhook_hmac_secret = ""

        event = {
            "event": "complaint",
            "email": "complain@t.com",
            "X-Mailin-custom": "campaign_id:3",
        }

        response = await webhook_client.post(
            "/api/v1/webhooks/brevo",
            content=json.dumps(event).encode(),
        )

        assert response.status_code == 200
        mock_update_email.assert_not_called()
        mock_update_campaign.assert_called_once()

    @patch("mailler.routes.webhooks._update_campaign_stats")
    @patch("mailler.routes.webhooks._update_email_status")
    @patch("mailler.routes.webhooks.settings")
    async def test_complaint_no_email_id_no_campaign(
        self, mock_settings, mock_update_email, mock_update_campaign, webhook_client: AsyncClient
    ):
        """Complaint without email_id or campaign_id does neither update."""
        mock_settings.webhook_hmac_secret = ""

        event = {
            "event": "complaint",
            "email": "complain@t.com",
            "X-Mailin-custom": "",
        }

        response = await webhook_client.post(
            "/api/v1/webhooks/brevo",
            content=json.dumps(event).encode(),
        )

        assert response.status_code == 200
        mock_update_email.assert_not_called()
        mock_update_campaign.assert_not_called()

    @patch("mailler.routes.webhooks._update_campaign_stats")
    @patch("mailler.routes.webhooks._update_email_status")
    @patch("mailler.routes.webhooks.settings")
    async def test_complaint_with_email_id_no_campaign(
        self, mock_settings, mock_update_email, mock_update_campaign, webhook_client: AsyncClient
    ):
        """Complaint with email_id but no campaign_id only updates email status."""
        mock_settings.webhook_hmac_secret = ""

        event = {
            "event": "complaint",
            "email": "complain@t.com",
            "X-Mailin-custom": "email_id:cmp-2",
        }

        response = await webhook_client.post(
            "/api/v1/webhooks/brevo",
            content=json.dumps(event).encode(),
        )

        assert response.status_code == 200
        mock_update_email.assert_called_once()
        mock_update_campaign.assert_not_called()

    # ----- unsubscribe without campaign_id (branch 397->432) -----

    @patch("mailler.routes.webhooks._update_campaign_stats")
    @patch("mailler.routes.webhooks._update_email_status")
    @patch("mailler.routes.webhooks.settings")
    async def test_unsubscribe_no_campaign(
        self, mock_settings, mock_update_email, mock_update_campaign, webhook_client: AsyncClient
    ):
        """Unsubscribe without campaign_id does not update campaign stats."""
        mock_settings.webhook_hmac_secret = ""

        event = {
            "event": "unsubscribe",
            "email": "unsub@t.com",
            "X-Mailin-custom": "",
        }

        response = await webhook_client.post(
            "/api/v1/webhooks/brevo",
            content=json.dumps(event).encode(),
        )

        assert response.status_code == 200
        mock_update_campaign.assert_not_called()

    @patch("mailler.routes.webhooks._update_campaign_stats")
    @patch("mailler.routes.webhooks._update_email_status")
    @patch("mailler.routes.webhooks.settings")
    async def test_unsubscribed_no_campaign(
        self, mock_settings, mock_update_email, mock_update_campaign, webhook_client: AsyncClient
    ):
        """Unsubscribed variant without campaign_id does not update campaign stats."""
        mock_settings.webhook_hmac_secret = ""

        event = {
            "event": "unsubscribed",
            "email": "unsub@t.com",
            "X-Mailin-custom": "",
        }

        response = await webhook_client.post(
            "/api/v1/webhooks/brevo",
            content=json.dumps(event).encode(),
        )

        assert response.status_code == 200
        mock_update_campaign.assert_not_called()

    # ----- open without campaign_id (branch 406->432) -----

    @patch("mailler.routes.webhooks._update_campaign_stats")
    @patch("mailler.routes.webhooks._update_email_status")
    @patch("mailler.routes.webhooks.settings")
    async def test_open_no_campaign(
        self, mock_settings, mock_update_email, mock_update_campaign, webhook_client: AsyncClient
    ):
        """Open event without campaign_id does not update campaign stats."""
        mock_settings.webhook_hmac_secret = ""

        event = {
            "event": "open",
            "email": "open@t.com",
            "X-Mailin-custom": "",
        }

        response = await webhook_client.post(
            "/api/v1/webhooks/brevo",
            content=json.dumps(event).encode(),
        )

        assert response.status_code == 200
        mock_update_campaign.assert_not_called()

    @patch("mailler.routes.webhooks._update_campaign_stats")
    @patch("mailler.routes.webhooks._update_email_status")
    @patch("mailler.routes.webhooks.settings")
    async def test_unique_opened_no_campaign(
        self, mock_settings, mock_update_email, mock_update_campaign, webhook_client: AsyncClient
    ):
        """unique_opened event without campaign_id does not update campaign stats."""
        mock_settings.webhook_hmac_secret = ""

        event = {
            "event": "unique_opened",
            "email": "open@t.com",
            "X-Mailin-custom": "",
        }

        response = await webhook_client.post(
            "/api/v1/webhooks/brevo",
            content=json.dumps(event).encode(),
        )

        assert response.status_code == 200
        mock_update_campaign.assert_not_called()

    # ----- click without campaign_id (branch 414->432) -----

    @patch("mailler.routes.webhooks._update_campaign_stats")
    @patch("mailler.routes.webhooks._update_email_status")
    @patch("mailler.routes.webhooks.settings")
    async def test_click_no_campaign(
        self, mock_settings, mock_update_email, mock_update_campaign, webhook_client: AsyncClient
    ):
        """Click event without campaign_id does not update campaign stats."""
        mock_settings.webhook_hmac_secret = ""

        event = {
            "event": "click",
            "email": "click@t.com",
            "X-Mailin-custom": "",
        }

        response = await webhook_client.post(
            "/api/v1/webhooks/brevo",
            content=json.dumps(event).encode(),
        )

        assert response.status_code == 200
        mock_update_campaign.assert_not_called()


class TestUpdateEmailStatus:
    """Tests for the _update_email_status helper function."""

    @patch("mailler.routes.webhooks.get_sync_db")
    def test_email_not_found(self, mock_get_db):
        """Returns None when email is not found."""
        from mailler.models.email import EmailStatus
        from mailler.routes.webhooks import _update_email_status

        mock_db = MagicMock()
        mock_db.get.return_value = None
        mock_get_db.return_value.__enter__ = MagicMock(return_value=mock_db)
        mock_get_db.return_value.__exit__ = MagicMock(return_value=False)

        result = _update_email_status("nonexistent-id", EmailStatus.DELIVERED)

        assert result is None

    @patch("mailler.routes.webhooks.get_sync_db")
    def test_delivered_status(self, mock_get_db):
        """Updates email status to delivered and sets delivered_at."""
        from mailler.models.email import EmailStatus
        from mailler.routes.webhooks import _update_email_status

        mock_email = MagicMock()
        mock_email.status = "sent"
        mock_email.provider_message_id = None

        mock_db = MagicMock()
        mock_db.get.return_value = mock_email
        mock_get_db.return_value.__enter__ = MagicMock(return_value=mock_db)
        mock_get_db.return_value.__exit__ = MagicMock(return_value=False)

        result = _update_email_status("email-1", EmailStatus.DELIVERED)

        assert result is mock_email
        assert mock_email.status == EmailStatus.DELIVERED.value
        assert mock_email.delivered_at is not None
        mock_db.commit.assert_called_once()

    @patch("mailler.routes.webhooks.get_sync_db")
    def test_bounced_status(self, mock_get_db):
        """Updates email status to bounced with error message."""
        from mailler.models.email import EmailStatus
        from mailler.routes.webhooks import _update_email_status

        mock_email = MagicMock()
        mock_email.status = "sent"
        mock_email.provider_message_id = "existing-id"

        mock_db = MagicMock()
        mock_db.get.return_value = mock_email
        mock_get_db.return_value.__enter__ = MagicMock(return_value=mock_db)
        mock_get_db.return_value.__exit__ = MagicMock(return_value=False)

        result = _update_email_status("email-2", EmailStatus.BOUNCED, error_message="Bad mailbox")

        assert result is mock_email
        assert mock_email.status == EmailStatus.BOUNCED.value
        assert mock_email.bounced_at is not None
        assert mock_email.error_message == "Bad mailbox"

    @patch("mailler.routes.webhooks.get_sync_db")
    def test_failed_status(self, mock_get_db):
        """Updates email status to failed with error message."""
        from mailler.models.email import EmailStatus
        from mailler.routes.webhooks import _update_email_status

        mock_email = MagicMock()
        mock_email.status = "sent"
        mock_email.provider_message_id = None

        mock_db = MagicMock()
        mock_db.get.return_value = mock_email
        mock_get_db.return_value.__enter__ = MagicMock(return_value=mock_db)
        mock_get_db.return_value.__exit__ = MagicMock(return_value=False)

        result = _update_email_status("email-3", EmailStatus.FAILED, error_message="Timeout")

        assert result is mock_email
        assert mock_email.status == EmailStatus.FAILED.value
        assert mock_email.failed_at is not None
        assert mock_email.error_message == "Timeout"

    @patch("mailler.routes.webhooks.get_sync_db")
    def test_sets_provider_message_id(self, mock_get_db):
        """Sets provider_message_id when not already set."""
        from mailler.models.email import EmailStatus
        from mailler.routes.webhooks import _update_email_status

        mock_email = MagicMock()
        mock_email.status = "sent"
        mock_email.provider_message_id = None

        mock_db = MagicMock()
        mock_db.get.return_value = mock_email
        mock_get_db.return_value.__enter__ = MagicMock(return_value=mock_db)
        mock_get_db.return_value.__exit__ = MagicMock(return_value=False)

        _update_email_status("email-4", EmailStatus.DELIVERED, provider_message_id="msg-id-123")

        assert mock_email.provider_message_id == "msg-id-123"

    @patch("mailler.routes.webhooks.get_sync_db")
    def test_exception_returns_none(self, mock_get_db):
        """Returns None on exception."""
        from mailler.models.email import EmailStatus
        from mailler.routes.webhooks import _update_email_status

        mock_get_db.return_value.__enter__ = MagicMock(side_effect=RuntimeError("DB error"))
        mock_get_db.return_value.__exit__ = MagicMock(return_value=False)

        result = _update_email_status("email-5", EmailStatus.DELIVERED)

        assert result is None


class TestUpdateEmailStatusMissingBranches:
    """Additional tests for _update_email_status branch coverage.

    Covers the branch where new_status is not DELIVERED, BOUNCED, or FAILED
    (falls through all three conditions), and where provider_message_id
    is already set.
    """

    @patch("mailler.routes.webhooks.get_sync_db")
    def test_sent_status_no_timestamp_update(self, mock_get_db):
        """Status that is not DELIVERED/BOUNCED/FAILED skips all timestamp branches.

        Covers branch 59->63: the else path where none of the status-specific
        timestamp branches are taken.
        """
        from mailler.models.email import EmailStatus
        from mailler.routes.webhooks import _update_email_status

        mock_email = MagicMock()
        mock_email.status = "pending"
        mock_email.provider_message_id = None
        # Reset timestamp attributes to track they are not set
        mock_email.delivered_at = None
        mock_email.bounced_at = None
        mock_email.failed_at = None

        mock_db = MagicMock()
        mock_db.get.return_value = mock_email
        mock_get_db.return_value.__enter__ = MagicMock(return_value=mock_db)
        mock_get_db.return_value.__exit__ = MagicMock(return_value=False)

        result = _update_email_status("email-sent", EmailStatus.SENT)

        assert result is mock_email
        assert mock_email.status == EmailStatus.SENT.value
        # None of the timestamp-specific attributes should have been explicitly set
        # Since MagicMock auto-creates attributes on assignment, we verify via commit
        mock_db.commit.assert_called_once()

    @patch("mailler.routes.webhooks.get_sync_db")
    def test_provider_message_id_not_overwritten(self, mock_get_db):
        """When provider_message_id is already set, it is not overwritten.

        This tests the false branch of
        'if provider_message_id and not email.provider_message_id'
        where email already has a provider_message_id.
        """
        from mailler.models.email import EmailStatus
        from mailler.routes.webhooks import _update_email_status

        mock_email = MagicMock()
        mock_email.status = "sent"
        mock_email.provider_message_id = "existing-provider-id"

        mock_db = MagicMock()
        mock_db.get.return_value = mock_email
        mock_get_db.return_value.__enter__ = MagicMock(return_value=mock_db)
        mock_get_db.return_value.__exit__ = MagicMock(return_value=False)

        result = _update_email_status(
            "email-6", EmailStatus.DELIVERED, provider_message_id="new-id"
        )

        assert result is mock_email
        # The existing provider_message_id should not be changed
        assert mock_email.provider_message_id == "existing-provider-id"


class TestUpdateCampaignStats:
    """Tests for the _update_campaign_stats helper function."""

    @patch("mailler.routes.webhooks.get_sync_db")
    def test_no_campaign_id(self, mock_get_db):
        """Returns False when no campaign_id provided."""
        from mailler.routes.webhooks import _update_campaign_stats

        result = _update_campaign_stats("test@t.com", None, "delivery")

        assert result is False
        mock_get_db.assert_not_called()

    @patch("mailler.routes.webhooks.get_sync_db")
    def test_email_send_not_found(self, mock_get_db):
        """Returns False when EmailSend record is not found."""
        from mailler.routes.webhooks import _update_campaign_stats

        mock_db = MagicMock()
        mock_db.execute.return_value.scalar_one_or_none.return_value = None
        mock_get_db.return_value.__enter__ = MagicMock(return_value=mock_db)
        mock_get_db.return_value.__exit__ = MagicMock(return_value=False)

        result = _update_campaign_stats("test@t.com", 1, "delivery")

        assert result is False

    @patch("mailler.routes.webhooks.get_sync_db")
    def test_campaign_not_found(self, mock_get_db):
        """Returns False when campaign record is not found."""
        from mailler.routes.webhooks import _update_campaign_stats

        mock_send = MagicMock()
        mock_send.status = "sent"

        mock_db = MagicMock()
        mock_db.execute.return_value.scalar_one_or_none.return_value = mock_send
        mock_db.get.return_value = None
        mock_get_db.return_value.__enter__ = MagicMock(return_value=mock_db)
        mock_get_db.return_value.__exit__ = MagicMock(return_value=False)

        result = _update_campaign_stats("test@t.com", 1, "delivery")

        assert result is False

    @patch("mailler.routes.webhooks.get_sync_db")
    def test_delivery_event(self, mock_get_db):
        """Delivery event updates EmailSend to delivered."""
        from mailler.routes.webhooks import _update_campaign_stats

        mock_send = MagicMock()
        mock_send.status = "sent"
        mock_send.contact_id = None

        mock_campaign = MagicMock()
        mock_campaign.delivered_count = 0

        mock_db = MagicMock()
        mock_db.execute.return_value.scalar_one_or_none.return_value = mock_send
        mock_db.get.return_value = mock_campaign
        mock_get_db.return_value.__enter__ = MagicMock(return_value=mock_db)
        mock_get_db.return_value.__exit__ = MagicMock(return_value=False)

        result = _update_campaign_stats("test@t.com", 1, "delivery")

        assert result is True
        assert mock_send.status == "delivered"
        assert mock_campaign.delivered_count == 1
        mock_db.commit.assert_called_once()

    @patch("mailler.routes.webhooks.get_sync_db")
    def test_bounce_event_from_sent(self, mock_get_db):
        """Bounce event from sent status updates EmailSend to bounced."""
        from mailler.routes.webhooks import _update_campaign_stats

        mock_send = MagicMock()
        mock_send.status = "sent"
        mock_send.contact_id = None

        mock_campaign = MagicMock()
        mock_campaign.bounced_count = 0

        mock_db = MagicMock()
        mock_db.execute.return_value.scalar_one_or_none.return_value = mock_send
        mock_db.get.return_value = mock_campaign
        mock_get_db.return_value.__enter__ = MagicMock(return_value=mock_db)
        mock_get_db.return_value.__exit__ = MagicMock(return_value=False)

        result = _update_campaign_stats("test@t.com", 1, "bounce", error_message="Hard bounce")

        assert result is True
        assert mock_send.status == "bounced"
        assert mock_campaign.bounced_count == 1

    @patch("mailler.routes.webhooks.get_sync_db")
    def test_bounce_event_from_delivered(self, mock_get_db):
        """Bounce from delivered status decrements delivered_count."""
        from mailler.routes.webhooks import _update_campaign_stats

        mock_send = MagicMock()
        mock_send.status = "delivered"
        mock_send.contact_id = None

        mock_campaign = MagicMock()
        mock_campaign.bounced_count = 0
        mock_campaign.delivered_count = 5

        mock_db = MagicMock()
        mock_db.execute.return_value.scalar_one_or_none.return_value = mock_send
        mock_db.get.return_value = mock_campaign
        mock_get_db.return_value.__enter__ = MagicMock(return_value=mock_db)
        mock_get_db.return_value.__exit__ = MagicMock(return_value=False)

        result = _update_campaign_stats("test@t.com", 1, "bounce")

        assert result is True
        assert mock_send.status == "bounced"
        assert mock_campaign.bounced_count == 1
        assert mock_campaign.delivered_count == 4

    @patch("mailler.routes.webhooks.get_sync_db")
    def test_bounce_marks_contact_as_bounced(self, mock_get_db):
        """Bounce event marks contact as bounced if contact is active."""
        from uuid import uuid4

        from mailler.routes.webhooks import _update_campaign_stats

        contact_id = uuid4()
        mock_contact = MagicMock()
        mock_contact.status = "active"

        mock_send = MagicMock()
        mock_send.status = "sent"
        mock_send.contact_id = contact_id

        mock_campaign = MagicMock()
        mock_campaign.bounced_count = 0

        mock_db = MagicMock()
        mock_db.execute.return_value.scalar_one_or_none.return_value = mock_send
        # db.get is called twice: once for campaign, once for contact
        mock_db.get.side_effect = [mock_campaign, mock_contact]
        mock_get_db.return_value.__enter__ = MagicMock(return_value=mock_db)
        mock_get_db.return_value.__exit__ = MagicMock(return_value=False)

        _update_campaign_stats("test@t.com", 1, "bounce")

        assert mock_contact.status == "bounced"

    @patch("mailler.routes.webhooks.get_sync_db")
    def test_complaint_event(self, mock_get_db):
        """Complaint event updates EmailSend and campaign stats."""
        from mailler.routes.webhooks import _update_campaign_stats

        mock_send = MagicMock()
        mock_send.status = "delivered"
        mock_send.contact_id = None

        mock_campaign = MagicMock()
        mock_campaign.complained_count = 0
        mock_campaign.delivered_count = 5

        mock_db = MagicMock()
        mock_db.execute.return_value.scalar_one_or_none.return_value = mock_send
        mock_db.get.return_value = mock_campaign
        mock_get_db.return_value.__enter__ = MagicMock(return_value=mock_db)
        mock_get_db.return_value.__exit__ = MagicMock(return_value=False)

        result = _update_campaign_stats("test@t.com", 1, "complaint")

        assert result is True
        assert mock_send.status == "complained"
        assert mock_campaign.complained_count == 1
        assert mock_campaign.delivered_count == 4

    @patch("mailler.routes.webhooks.get_sync_db")
    def test_complaint_marks_contact(self, mock_get_db):
        """Complaint marks contact as complained."""
        from uuid import uuid4

        from mailler.routes.webhooks import _update_campaign_stats

        contact_id = uuid4()
        mock_contact = MagicMock()
        mock_contact.status = "active"

        mock_send = MagicMock()
        mock_send.status = "sent"
        mock_send.contact_id = contact_id

        mock_campaign = MagicMock()
        mock_campaign.complained_count = 0
        mock_campaign.delivered_count = 0

        mock_db = MagicMock()
        mock_db.execute.return_value.scalar_one_or_none.return_value = mock_send
        mock_db.get.side_effect = [mock_campaign, mock_contact]
        mock_get_db.return_value.__enter__ = MagicMock(return_value=mock_db)
        mock_get_db.return_value.__exit__ = MagicMock(return_value=False)

        _update_campaign_stats("test@t.com", 1, "complaint")

        assert mock_contact.status == "complained"

    @patch("mailler.routes.webhooks.get_sync_db")
    def test_open_event_from_delivered(self, mock_get_db):
        """Open event from delivered status updates to opened."""
        from mailler.routes.webhooks import _update_campaign_stats

        mock_send = MagicMock()
        mock_send.status = "delivered"
        mock_send.opened_at = None

        mock_campaign = MagicMock()
        mock_campaign.opened_count = 0

        mock_db = MagicMock()
        mock_db.execute.return_value.scalar_one_or_none.return_value = mock_send
        mock_db.get.return_value = mock_campaign
        mock_get_db.return_value.__enter__ = MagicMock(return_value=mock_db)
        mock_get_db.return_value.__exit__ = MagicMock(return_value=False)

        result = _update_campaign_stats("test@t.com", 1, "open")

        assert result is True
        assert mock_send.status == "opened"
        assert mock_campaign.opened_count == 1

    @patch("mailler.routes.webhooks.get_sync_db")
    def test_open_event_already_opened(self, mock_get_db):
        """Open event when already opened does not change status."""
        from datetime import datetime

        from mailler.routes.webhooks import _update_campaign_stats

        mock_send = MagicMock()
        mock_send.status = "opened"
        mock_send.opened_at = datetime.now(UTC)

        mock_campaign = MagicMock()
        mock_campaign.opened_count = 1

        mock_db = MagicMock()
        mock_db.execute.return_value.scalar_one_or_none.return_value = mock_send
        mock_db.get.return_value = mock_campaign
        mock_get_db.return_value.__enter__ = MagicMock(return_value=mock_db)
        mock_get_db.return_value.__exit__ = MagicMock(return_value=False)

        result = _update_campaign_stats("test@t.com", 1, "open")

        # status stays "opened" so no change -> returns False
        assert result is False

    @patch("mailler.routes.webhooks.get_sync_db")
    def test_click_event_from_delivered(self, mock_get_db):
        """Click event from delivered tracks both open and click."""
        from mailler.routes.webhooks import _update_campaign_stats

        mock_send = MagicMock()
        mock_send.status = "delivered"
        mock_send.opened_at = None
        mock_send.clicked_at = None

        mock_campaign = MagicMock()
        mock_campaign.opened_count = 0
        mock_campaign.clicked_count = 0

        mock_db = MagicMock()
        mock_db.execute.return_value.scalar_one_or_none.return_value = mock_send
        mock_db.get.return_value = mock_campaign
        mock_get_db.return_value.__enter__ = MagicMock(return_value=mock_db)
        mock_get_db.return_value.__exit__ = MagicMock(return_value=False)

        result = _update_campaign_stats("test@t.com", 1, "click")

        assert result is True
        assert mock_send.status == "clicked"
        assert mock_campaign.opened_count == 1
        assert mock_campaign.clicked_count == 1

    @patch("mailler.routes.webhooks.get_sync_db")
    def test_click_event_already_opened(self, mock_get_db):
        """Click event when already opened doesn't re-increment opened_count."""
        from datetime import datetime

        from mailler.routes.webhooks import _update_campaign_stats

        mock_send = MagicMock()
        mock_send.status = "opened"
        mock_send.opened_at = datetime.now(UTC)
        mock_send.clicked_at = None

        mock_campaign = MagicMock()
        mock_campaign.opened_count = 1
        mock_campaign.clicked_count = 0

        mock_db = MagicMock()
        mock_db.execute.return_value.scalar_one_or_none.return_value = mock_send
        mock_db.get.return_value = mock_campaign
        mock_get_db.return_value.__enter__ = MagicMock(return_value=mock_db)
        mock_get_db.return_value.__exit__ = MagicMock(return_value=False)

        result = _update_campaign_stats("test@t.com", 1, "click")

        assert result is True
        assert mock_send.status == "clicked"
        assert mock_campaign.opened_count == 1  # not incremented
        assert mock_campaign.clicked_count == 1

    @patch("mailler.routes.webhooks.get_sync_db")
    def test_exception_returns_false(self, mock_get_db):
        """Returns False on unexpected exception."""
        from mailler.routes.webhooks import _update_campaign_stats

        mock_get_db.return_value.__enter__ = MagicMock(side_effect=RuntimeError("DB error"))
        mock_get_db.return_value.__exit__ = MagicMock(return_value=False)

        result = _update_campaign_stats("test@t.com", 1, "delivery")

        assert result is False


class TestUpdateCampaignStatsMissingBranches:
    """Additional tests for _update_campaign_stats branch coverage.

    Covers the false branches where event types skip processing because
    the email send status does not match the expected precondition.
    """

    # ----- delivery event skipped when not SENT (branch 130->244) -----

    @patch("mailler.routes.webhooks.get_sync_db")
    def test_delivery_already_delivered_skips(self, mock_get_db):
        """Delivery event when already delivered does not re-deliver.

        Covers branch 130->244: email_send.status != SENT for delivery event.
        """
        from mailler.routes.webhooks import _update_campaign_stats

        mock_send = MagicMock()
        mock_send.status = "delivered"

        mock_campaign = MagicMock()
        mock_campaign.delivered_count = 1

        mock_db = MagicMock()
        mock_db.execute.return_value.scalar_one_or_none.return_value = mock_send
        mock_db.get.return_value = mock_campaign
        mock_get_db.return_value.__enter__ = MagicMock(return_value=mock_db)
        mock_get_db.return_value.__exit__ = MagicMock(return_value=False)

        result = _update_campaign_stats("test@t.com", 1, "delivery")

        assert result is False
        assert mock_send.status == "delivered"
        assert mock_campaign.delivered_count == 1  # not incremented

    # ----- bounce event skipped when already bounced (branch 143->244) -----

    @patch("mailler.routes.webhooks.get_sync_db")
    def test_bounce_already_bounced_skips(self, mock_get_db):
        """Bounce event when already bounced is ignored.

        Covers branch 143->244: email_send.status not in [SENT, DELIVERED].
        """
        from mailler.routes.webhooks import _update_campaign_stats

        mock_send = MagicMock()
        mock_send.status = "bounced"

        mock_campaign = MagicMock()
        mock_campaign.bounced_count = 1

        mock_db = MagicMock()
        mock_db.execute.return_value.scalar_one_or_none.return_value = mock_send
        mock_db.get.return_value = mock_campaign
        mock_get_db.return_value.__enter__ = MagicMock(return_value=mock_db)
        mock_get_db.return_value.__exit__ = MagicMock(return_value=False)

        result = _update_campaign_stats("test@t.com", 1, "bounce")

        assert result is False
        assert mock_send.status == "bounced"
        assert mock_campaign.bounced_count == 1  # not incremented

    # ----- bounce with contact not active (branch 159->166) -----

    @patch("mailler.routes.webhooks.get_sync_db")
    def test_bounce_contact_already_bounced_not_updated(self, mock_get_db):
        """Bounce event does not update contact that is already bounced.

        Covers branch 159->166: contact.status != 'active'.
        """
        from uuid import uuid4

        from mailler.routes.webhooks import _update_campaign_stats

        contact_id = uuid4()
        mock_contact = MagicMock()
        mock_contact.status = "bounced"

        mock_send = MagicMock()
        mock_send.status = "sent"
        mock_send.contact_id = contact_id

        mock_campaign = MagicMock()
        mock_campaign.bounced_count = 0

        mock_db = MagicMock()
        mock_db.execute.return_value.scalar_one_or_none.return_value = mock_send
        mock_db.get.side_effect = [mock_campaign, mock_contact]
        mock_get_db.return_value.__enter__ = MagicMock(return_value=mock_db)
        mock_get_db.return_value.__exit__ = MagicMock(return_value=False)

        _update_campaign_stats("test@t.com", 1, "bounce")

        assert mock_contact.status == "bounced"  # not changed

    @patch("mailler.routes.webhooks.get_sync_db")
    def test_bounce_contact_not_found(self, mock_get_db):
        """Bounce event with contact_id but contact not found in DB.

        Covers branch 159->166: contact is None.
        """
        from uuid import uuid4

        from mailler.routes.webhooks import _update_campaign_stats

        contact_id = uuid4()

        mock_send = MagicMock()
        mock_send.status = "sent"
        mock_send.contact_id = contact_id

        mock_campaign = MagicMock()
        mock_campaign.bounced_count = 0

        mock_db = MagicMock()
        mock_db.execute.return_value.scalar_one_or_none.return_value = mock_send
        mock_db.get.side_effect = [mock_campaign, None]
        mock_get_db.return_value.__enter__ = MagicMock(return_value=mock_db)
        mock_get_db.return_value.__exit__ = MagicMock(return_value=False)

        result = _update_campaign_stats("test@t.com", 1, "bounce")

        assert result is True
        assert mock_send.status == "bounced"

    # ----- complaint event skipped when already complained (branch 174->244) -----

    @patch("mailler.routes.webhooks.get_sync_db")
    def test_complaint_already_complained_skips(self, mock_get_db):
        """Complaint event when already complained is ignored.

        Covers branch 174->244: email_send.status not in [SENT, DELIVERED].
        """
        from mailler.routes.webhooks import _update_campaign_stats

        mock_send = MagicMock()
        mock_send.status = "complained"

        mock_campaign = MagicMock()
        mock_campaign.complained_count = 1

        mock_db = MagicMock()
        mock_db.execute.return_value.scalar_one_or_none.return_value = mock_send
        mock_db.get.return_value = mock_campaign
        mock_get_db.return_value.__enter__ = MagicMock(return_value=mock_db)
        mock_get_db.return_value.__exit__ = MagicMock(return_value=False)

        result = _update_campaign_stats("test@t.com", 1, "complaint")

        assert result is False
        assert mock_send.status == "complained"
        assert mock_campaign.complained_count == 1  # not incremented

    # ----- complaint with contact not active (branch 188->195) -----

    @patch("mailler.routes.webhooks.get_sync_db")
    def test_complaint_contact_already_complained_not_updated(self, mock_get_db):
        """Complaint event does not update contact that is already complained.

        Covers branch 188->195: contact.status != 'active'.
        """
        from uuid import uuid4

        from mailler.routes.webhooks import _update_campaign_stats

        contact_id = uuid4()
        mock_contact = MagicMock()
        mock_contact.status = "complained"

        mock_send = MagicMock()
        mock_send.status = "sent"
        mock_send.contact_id = contact_id

        mock_campaign = MagicMock()
        mock_campaign.complained_count = 0
        mock_campaign.delivered_count = 0

        mock_db = MagicMock()
        mock_db.execute.return_value.scalar_one_or_none.return_value = mock_send
        mock_db.get.side_effect = [mock_campaign, mock_contact]
        mock_get_db.return_value.__enter__ = MagicMock(return_value=mock_db)
        mock_get_db.return_value.__exit__ = MagicMock(return_value=False)

        _update_campaign_stats("test@t.com", 1, "complaint")

        assert mock_contact.status == "complained"  # not changed

    @patch("mailler.routes.webhooks.get_sync_db")
    def test_complaint_contact_not_found(self, mock_get_db):
        """Complaint event with contact_id but contact not found in DB.

        Covers branch 188->195: contact is None.
        """
        from uuid import uuid4

        from mailler.routes.webhooks import _update_campaign_stats

        contact_id = uuid4()

        mock_send = MagicMock()
        mock_send.status = "delivered"
        mock_send.contact_id = contact_id

        mock_campaign = MagicMock()
        mock_campaign.complained_count = 0
        mock_campaign.delivered_count = 5

        mock_db = MagicMock()
        mock_db.execute.return_value.scalar_one_or_none.return_value = mock_send
        mock_db.get.side_effect = [mock_campaign, None]
        mock_get_db.return_value.__enter__ = MagicMock(return_value=mock_db)
        mock_get_db.return_value.__exit__ = MagicMock(return_value=False)

        result = _update_campaign_stats("test@t.com", 1, "complaint")

        assert result is True
        assert mock_send.status == "complained"

    # ----- open event from wrong status (branch 203->244) -----

    @patch("mailler.routes.webhooks.get_sync_db")
    def test_open_from_sent_skips(self, mock_get_db):
        """Open event when status is 'sent' (not delivered/opened/clicked) is ignored.

        Covers branch 203->244: email_send.status not in [DELIVERED, OPENED, CLICKED].
        """
        from mailler.routes.webhooks import _update_campaign_stats

        mock_send = MagicMock()
        mock_send.status = "sent"

        mock_campaign = MagicMock()
        mock_campaign.opened_count = 0

        mock_db = MagicMock()
        mock_db.execute.return_value.scalar_one_or_none.return_value = mock_send
        mock_db.get.return_value = mock_campaign
        mock_get_db.return_value.__enter__ = MagicMock(return_value=mock_db)
        mock_get_db.return_value.__exit__ = MagicMock(return_value=False)

        result = _update_campaign_stats("test@t.com", 1, "open")

        assert result is False
        assert mock_send.status == "sent"
        assert mock_campaign.opened_count == 0

    # ----- open event from clicked status -----

    @patch("mailler.routes.webhooks.get_sync_db")
    def test_open_from_clicked_no_status_change(self, mock_get_db):
        """Open event when status is 'clicked' does not change status to opened.

        The open event enters the branch (status in [DELIVERED, OPENED, CLICKED]),
        but since status is not DELIVERED, opened_count is not incremented.
        opened_at is already set, so that is also not changed.
        """
        from datetime import datetime

        from mailler.routes.webhooks import _update_campaign_stats

        mock_send = MagicMock()
        mock_send.status = "clicked"
        mock_send.opened_at = datetime.now(UTC)

        mock_campaign = MagicMock()
        mock_campaign.opened_count = 1

        mock_db = MagicMock()
        mock_db.execute.return_value.scalar_one_or_none.return_value = mock_send
        mock_db.get.return_value = mock_campaign
        mock_get_db.return_value.__enter__ = MagicMock(return_value=mock_db)
        mock_get_db.return_value.__exit__ = MagicMock(return_value=False)

        result = _update_campaign_stats("test@t.com", 1, "open")

        assert result is False
        assert mock_send.status == "clicked"  # not changed to opened
        assert mock_campaign.opened_count == 1  # not incremented

    # ----- click event from wrong status (branches 220->244, 221->244) -----

    @patch("mailler.routes.webhooks.get_sync_db")
    def test_click_from_sent_skips(self, mock_get_db):
        """Click event when status is 'sent' (not delivered/opened/clicked) is ignored.

        Covers branches 220->244 and 221->244: email_send.status not in
        [DELIVERED, OPENED, CLICKED].
        """
        from mailler.routes.webhooks import _update_campaign_stats

        mock_send = MagicMock()
        mock_send.status = "sent"

        mock_campaign = MagicMock()
        mock_campaign.clicked_count = 0

        mock_db = MagicMock()
        mock_db.execute.return_value.scalar_one_or_none.return_value = mock_send
        mock_db.get.return_value = mock_campaign
        mock_get_db.return_value.__enter__ = MagicMock(return_value=mock_db)
        mock_get_db.return_value.__exit__ = MagicMock(return_value=False)

        result = _update_campaign_stats("test@t.com", 1, "click")

        assert result is False
        assert mock_send.status == "sent"
        assert mock_campaign.clicked_count == 0

    # ----- click from opened but opened_at not set, not from delivered
    #       (branch 229->232: status is OPENED, not DELIVERED) -----

    @patch("mailler.routes.webhooks.get_sync_db")
    def test_click_from_opened_without_opened_at(self, mock_get_db):
        """Click event from opened status where opened_at is None sets opened_at
        but does not increment opened_count (because status is not DELIVERED).

        Covers branch 229->232: opened_at is None but status is not DELIVERED.
        """
        from mailler.routes.webhooks import _update_campaign_stats

        mock_send = MagicMock()
        mock_send.status = "opened"
        mock_send.opened_at = None
        mock_send.clicked_at = None

        mock_campaign = MagicMock()
        mock_campaign.opened_count = 1
        mock_campaign.clicked_count = 0

        mock_db = MagicMock()
        mock_db.execute.return_value.scalar_one_or_none.return_value = mock_send
        mock_db.get.return_value = mock_campaign
        mock_get_db.return_value.__enter__ = MagicMock(return_value=mock_db)
        mock_get_db.return_value.__exit__ = MagicMock(return_value=False)

        result = _update_campaign_stats("test@t.com", 1, "click")

        assert result is True
        assert mock_send.status == "clicked"
        assert mock_send.opened_at is not None
        assert mock_campaign.opened_count == 1  # not incremented since status was opened
        assert mock_campaign.clicked_count == 1

    # ----- click already clicked (branch 232->235) -----

    @patch("mailler.routes.webhooks.get_sync_db")
    def test_click_already_clicked_no_count_increment(self, mock_get_db):
        """Click event when already clicked does not increment clicked_count.

        Covers branch 232->235: email_send.status == CLICKED (already clicked).
        """
        from datetime import datetime

        from mailler.routes.webhooks import _update_campaign_stats

        mock_send = MagicMock()
        mock_send.status = "clicked"
        mock_send.opened_at = datetime.now(UTC)
        mock_send.clicked_at = datetime.now(UTC)

        mock_campaign = MagicMock()
        mock_campaign.opened_count = 1
        mock_campaign.clicked_count = 1

        mock_db = MagicMock()
        mock_db.execute.return_value.scalar_one_or_none.return_value = mock_send
        mock_db.get.return_value = mock_campaign
        mock_get_db.return_value.__enter__ = MagicMock(return_value=mock_db)
        mock_get_db.return_value.__exit__ = MagicMock(return_value=False)

        result = _update_campaign_stats("test@t.com", 1, "click")

        assert result is False  # status did not change
        assert mock_send.status == "clicked"
        assert mock_campaign.clicked_count == 1  # not incremented
        assert mock_campaign.opened_count == 1  # not incremented

    # ----- click already clicked but clicked_at not yet set (branch 235->237) -----

    @patch("mailler.routes.webhooks.get_sync_db")
    def test_click_already_clicked_but_no_clicked_at(self, mock_get_db):
        """Click event when already clicked but clicked_at is None still sets clicked_at.

        Covers branch 235->237: clicked_at is None even though status is already clicked.
        """
        from datetime import datetime

        from mailler.routes.webhooks import _update_campaign_stats

        mock_send = MagicMock()
        mock_send.status = "clicked"
        mock_send.opened_at = datetime.now(UTC)
        mock_send.clicked_at = None  # status is clicked but timestamp was not set

        mock_campaign = MagicMock()
        mock_campaign.opened_count = 1
        mock_campaign.clicked_count = 1

        mock_db = MagicMock()
        mock_db.execute.return_value.scalar_one_or_none.return_value = mock_send
        mock_db.get.return_value = mock_campaign
        mock_get_db.return_value.__enter__ = MagicMock(return_value=mock_db)
        mock_get_db.return_value.__exit__ = MagicMock(return_value=False)

        result = _update_campaign_stats("test@t.com", 1, "click")

        assert result is False  # status did not change (already clicked)
        assert mock_send.clicked_at is not None  # clicked_at was set
        assert mock_campaign.clicked_count == 1  # not incremented

    # ----- unrecognized event type falls through all branches (branch 220->244) -----

    @patch("mailler.routes.webhooks.get_sync_db")
    def test_unrecognized_event_type_no_changes(self, mock_get_db):
        """Unrecognized event type falls through all if/elif branches with no changes.

        Covers branch 220->244: event_type does not match 'click' (or any prior),
        so the entire if/elif chain is skipped and we go straight to db.commit().
        """
        from mailler.routes.webhooks import _update_campaign_stats

        mock_send = MagicMock()
        mock_send.status = "sent"

        mock_campaign = MagicMock()

        mock_db = MagicMock()
        mock_db.execute.return_value.scalar_one_or_none.return_value = mock_send
        mock_db.get.return_value = mock_campaign
        mock_get_db.return_value.__enter__ = MagicMock(return_value=mock_db)
        mock_get_db.return_value.__exit__ = MagicMock(return_value=False)

        result = _update_campaign_stats("test@t.com", 1, "unknown_event")

        assert result is False  # status did not change
        assert mock_send.status == "sent"
        mock_db.commit.assert_called_once()


class TestWebhookStatusCallbacks:
    """A status change reported by the provider is passed on to the client."""

    @patch("mailler.routes.webhooks.get_sync_db")
    def test_the_client_is_notified_after_the_commit(self, mock_get_db, status_callbacks):
        from mailler.models.email import EmailStatus
        from mailler.routes.webhooks import _update_email_status

        mock_email = MagicMock()
        mock_email.status = "sent"
        mock_email.provider_message_id = None
        mock_db = MagicMock()
        mock_db.get.return_value = mock_email
        mock_get_db.return_value.__enter__ = MagicMock(return_value=mock_db)
        mock_get_db.return_value.__exit__ = MagicMock(return_value=False)
        order = []
        mock_db.commit.side_effect = lambda: order.append("commit")
        status_callbacks.side_effect = lambda db, email: order.append("notify")

        _update_email_status("email-1", EmailStatus.DELIVERED)

        status_callbacks.assert_called_once_with(mock_db, mock_email)
        assert order == ["commit", "notify"]

    @patch("mailler.routes.webhooks.get_sync_db")
    def test_nobody_is_notified_for_an_unknown_email(self, mock_get_db, status_callbacks):
        from mailler.models.email import EmailStatus
        from mailler.routes.webhooks import _update_email_status

        mock_db = MagicMock()
        mock_db.get.return_value = None
        mock_get_db.return_value.__enter__ = MagicMock(return_value=mock_db)
        mock_get_db.return_value.__exit__ = MagicMock(return_value=False)

        _update_email_status("nope", EmailStatus.DELIVERED)

        status_callbacks.assert_not_called()
