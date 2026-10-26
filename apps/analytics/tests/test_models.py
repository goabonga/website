# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for analytics.models module."""

from analytics.models import Base, Campaign, CampaignClick, Event, Pixel, PixelOpen, Session


class TestModelImports:
    """Tests that all models are properly exported."""

    def test_base_exists(self):
        assert Base is not None

    def test_session_model(self):
        assert Session.__tablename__ == "analytics_sessions"

    def test_event_model(self):
        assert Event.__tablename__ == "analytics_events"

    def test_campaign_model(self):
        assert Campaign.__tablename__ == "analytics_campaigns"

    def test_pixel_model(self):
        assert Pixel.__tablename__ == "analytics_pixels"

    def test_pixel_open_model(self):
        assert PixelOpen.__tablename__ == "analytics_pixel_opens"

    def test_campaign_click_model(self):
        assert CampaignClick.__tablename__ == "analytics_campaign_clicks"


class TestSessionModel:
    """Tests for Session model."""

    def test_repr(self):
        session = Session()
        session.session_id = "test-123"
        assert repr(session) == "<Session test-123>"


class TestEventModel:
    """Tests for Event model."""

    def test_repr(self):
        from datetime import datetime

        event = Event()
        event.event_type = "page_view"
        event.timestamp = datetime(2025, 1, 1)
        assert "page_view" in repr(event)


class TestCampaignModel:
    """Tests for Campaign model."""

    def test_repr(self):
        campaign = Campaign()
        campaign.name = "Test Campaign"
        assert repr(campaign) == "<Campaign Test Campaign>"


class TestPixelModel:
    """Tests for Pixel model."""

    def test_repr(self):
        pixel = Pixel()
        pixel.pixel_key = "pxl-123"
        assert repr(pixel) == "<Pixel pxl-123>"


class TestPixelOpenModel:
    """Tests for PixelOpen model."""

    def test_repr(self):
        import uuid
        from datetime import datetime

        pixel_open = PixelOpen()
        pixel_open.pixel_id = uuid.uuid4()
        pixel_open.opened_at = datetime(2025, 1, 1)
        assert "PixelOpen" in repr(pixel_open)


class TestCampaignClickModel:
    """Tests for CampaignClick model."""

    def test_repr(self):
        import uuid
        from datetime import datetime

        click = CampaignClick()
        click.campaign_id = uuid.uuid4()
        click.clicked_at = datetime(2025, 1, 1)
        assert "CampaignClick" in repr(click)


class TestSchema:
    """Tests for the table definitions."""

    def test_tables_registered_on_base(self):
        assert {
            "analytics_sessions",
            "analytics_campaign_clicks",
            "analytics_events",
            "analytics_pixel_opens",
            "analytics_pixels",
            "analytics_campaigns",
        } <= set(Base.metadata.tables)

    def test_session_id_is_unique_and_indexed(self):
        column = Session.__table__.c.session_id
        assert column.unique
        assert column.index

    def test_session_timestamps_have_defaults(self):
        table = Session.__table__
        assert table.c.first_seen.default is not None
        assert table.c.last_seen.default is not None
        assert table.c.last_seen.onupdate is not None

    def test_event_references_session_with_cascade(self):
        (foreign_key,) = Event.__table__.c.session_id.foreign_keys
        assert foreign_key.column.table.name == "analytics_sessions"
        assert foreign_key.ondelete == "CASCADE"

    def test_session_events_relationship_cascades_deletes(self):
        relationship = Session.__mapper__.relationships["events"]
        assert "delete-orphan" in relationship.cascade
        assert relationship.back_populates == "session"

    def test_event_composite_index(self):
        names = {index.name for index in Event.__table__.indexes}
        assert "ix_analytics_events_type_timestamp" in names


class TestCampaignSchema:
    """Tests for the campaign and pixel table definitions."""

    def test_tracking_key_is_unique_and_indexed(self):
        column = Campaign.__table__.c.tracking_key
        assert column.unique
        assert column.index

    def test_pixel_key_is_unique_and_indexed(self):
        column = Pixel.__table__.c.pixel_key
        assert column.unique
        assert column.index

    def test_campaign_counters_default_to_zero(self):
        table = Campaign.__table__
        assert table.c.click_count.default.arg == 0
        assert table.c.unique_click_count.default.arg == 0
        assert Pixel.__table__.c.open_count.default.arg == 0

    def test_campaign_is_active_by_default(self):
        assert Campaign.__table__.c.is_active.default.arg is True

    def test_pixel_references_campaign_with_cascade(self):
        (foreign_key,) = Pixel.__table__.c.campaign_id.foreign_keys
        assert foreign_key.column.table.name == "analytics_campaigns"
        assert foreign_key.ondelete == "CASCADE"

    def test_pixel_open_references_pixel_with_cascade(self):
        (foreign_key,) = PixelOpen.__table__.c.pixel_id.foreign_keys
        assert foreign_key.column.table.name == "analytics_pixels"
        assert foreign_key.ondelete == "CASCADE"

    def test_campaign_pixels_relationship_cascades_deletes(self):
        relationship = Campaign.__mapper__.relationships["pixels"]
        assert "delete-orphan" in relationship.cascade

    def test_pixel_opens_relationship_cascades_deletes(self):
        relationship = Pixel.__mapper__.relationships["opens"]
        assert "delete-orphan" in relationship.cascade


class TestCampaignClickSchema:
    """Tests for the campaign click table definition."""

    def test_click_references_campaign_with_cascade(self):
        (foreign_key,) = CampaignClick.__table__.c.campaign_id.foreign_keys
        assert foreign_key.column.table.name == "analytics_campaigns"
        assert foreign_key.ondelete == "CASCADE"

    def test_campaign_clicks_relationship_cascades_deletes(self):
        relationship = Campaign.__mapper__.relationships["clicks"]
        assert "delete-orphan" in relationship.cascade
        assert relationship.back_populates == "campaign"
