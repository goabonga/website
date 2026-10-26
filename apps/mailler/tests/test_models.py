# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for model properties and computed fields."""

from unittest.mock import MagicMock

from mailler.models.campaign import EmailCampaign
from mailler.models.contact import Contact, ContactGroup, ContactStatus


class TestContactFullName:
    """Tests for Contact.full_name property."""

    def _make_contact(self, first_name=None, last_name=None):
        mock = MagicMock(spec=[])
        mock.first_name = first_name
        mock.last_name = last_name
        return mock

    def test_both_names(self):
        c = self._make_contact("John", "Doe")
        assert Contact.full_name.fget(c) == "John Doe"

    def test_first_name_only(self):
        c = self._make_contact("John", None)
        assert Contact.full_name.fget(c) == "John"

    def test_last_name_only(self):
        c = self._make_contact(None, "Doe")
        assert Contact.full_name.fget(c) == "Doe"

    def test_no_names(self):
        c = self._make_contact(None, None)
        assert Contact.full_name.fget(c) == ""


class TestContactGroupMemberCount:
    """Tests for ContactGroup.member_count property."""

    def test_counts_active_only(self):
        active_contact = MagicMock()
        active_contact.status = ContactStatus.ACTIVE.value

        bounced_contact = MagicMock()
        bounced_contact.status = ContactStatus.BOUNCED.value

        unsub_contact = MagicMock()
        unsub_contact.status = ContactStatus.UNSUBSCRIBED.value

        m1 = MagicMock()
        m1.contact = active_contact
        m2 = MagicMock()
        m2.contact = bounced_contact
        m3 = MagicMock()
        m3.contact = unsub_contact

        group = MagicMock(spec=[])
        group.members = [m1, m2, m3]

        assert ContactGroup.member_count.fget(group) == 1

    def test_empty_group(self):
        group = MagicMock(spec=[])
        group.members = []
        assert ContactGroup.member_count.fget(group) == 0

    def test_null_contact_skipped(self):
        member = MagicMock()
        member.contact = None
        group = MagicMock(spec=[])
        group.members = [member]
        assert ContactGroup.member_count.fget(group) == 0


class TestContactGroupContacts:
    """Tests for ContactGroup.contacts property."""

    def test_returns_contacts(self):
        contact = MagicMock()
        member = MagicMock()
        member.contact = contact
        group = MagicMock(spec=[])
        group.members = [member]
        assert ContactGroup.contacts.fget(group) == [contact]

    def test_skips_null_contacts(self):
        member = MagicMock()
        member.contact = None
        group = MagicMock(spec=[])
        group.members = [member]
        assert ContactGroup.contacts.fget(group) == []


class TestContactGroups:
    """Tests for Contact.groups property."""

    def test_returns_groups(self):
        grp = MagicMock()
        membership = MagicMock()
        membership.group = grp
        contact = MagicMock(spec=[])
        contact.group_memberships = [membership]
        assert Contact.groups.fget(contact) == [grp]

    def test_skips_null_groups(self):
        membership = MagicMock()
        membership.group = None
        contact = MagicMock(spec=[])
        contact.group_memberships = [membership]
        assert Contact.groups.fget(contact) == []


class TestClientOwnership:
    """Contacts and groups are owned by a client and unique inside it."""

    @staticmethod
    def _unique_constraints(model):
        return {
            c.name: [col.name for col in c.columns]
            for c in model.__table__.constraints
            if c.__class__.__name__ == "UniqueConstraint"
        }

    def test_contact_email_is_unique_per_client(self):
        assert not Contact.__table__.columns["email"].unique
        assert self._unique_constraints(Contact) == {
            "uq_contacts_client_email": ["client_id", "email"]
        }

    def test_group_slug_is_unique_per_client(self):
        assert not ContactGroup.__table__.columns["slug"].unique
        assert self._unique_constraints(ContactGroup) == {
            "uq_contact_groups_client_slug": ["client_id", "slug"]
        }

    def test_client_is_required_and_indexed(self):
        for model in (Contact, ContactGroup):
            column = model.__table__.columns["client_id"]
            assert column.nullable is False
            assert column.index


class TestEmailCampaignProgressPercent:
    """Tests for EmailCampaign.progress_percent property."""

    def _make_campaign(self, **kwargs):
        c = MagicMock(spec=[])
        for k, v in kwargs.items():
            setattr(c, k, v)
        return c

    def test_normal(self):
        c = self._make_campaign(total_recipients=100, sent_count=50)
        assert EmailCampaign.progress_percent.fget(c) == 50.0

    def test_zero_recipients(self):
        c = self._make_campaign(total_recipients=0, sent_count=0)
        assert EmailCampaign.progress_percent.fget(c) == 0.0

    def test_rounding(self):
        c = self._make_campaign(total_recipients=3, sent_count=1)
        assert EmailCampaign.progress_percent.fget(c) == 33.3


class TestEmailCampaignOpenRate:
    """Tests for EmailCampaign.open_rate property."""

    def test_normal(self):
        c = MagicMock(spec=[])
        c.delivered_count = 100
        c.opened_count = 25
        assert EmailCampaign.open_rate.fget(c) == 25.0

    def test_zero_delivered(self):
        c = MagicMock(spec=[])
        c.delivered_count = 0
        c.opened_count = 0
        assert EmailCampaign.open_rate.fget(c) == 0.0


class TestEmailCampaignClickRate:
    """Tests for EmailCampaign.click_rate property."""

    def test_normal(self):
        c = MagicMock(spec=[])
        c.delivered_count = 200
        c.clicked_count = 10
        assert EmailCampaign.click_rate.fget(c) == 5.0

    def test_zero_delivered(self):
        c = MagicMock(spec=[])
        c.delivered_count = 0
        c.clicked_count = 0
        assert EmailCampaign.click_rate.fget(c) == 0.0


class TestEmailCampaignBounceRate:
    """Tests for EmailCampaign.bounce_rate property."""

    def test_normal(self):
        c = MagicMock(spec=[])
        c.sent_count = 100
        c.bounced_count = 5
        assert EmailCampaign.bounce_rate.fget(c) == 5.0

    def test_zero_sent(self):
        c = MagicMock(spec=[])
        c.sent_count = 0
        c.bounced_count = 0
        assert EmailCampaign.bounce_rate.fget(c) == 0.0


class TestEmailCampaignComplaintRate:
    """Tests for EmailCampaign.complaint_rate property."""

    def test_normal(self):
        c = MagicMock(spec=[])
        c.delivered_count = 1000
        c.complained_count = 3
        assert EmailCampaign.complaint_rate.fget(c) == 0.3

    def test_zero_delivered(self):
        c = MagicMock(spec=[])
        c.delivered_count = 0
        c.complained_count = 0
        assert EmailCampaign.complaint_rate.fget(c) == 0.0
