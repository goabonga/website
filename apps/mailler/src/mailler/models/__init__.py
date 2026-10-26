# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Database models for Mailler."""

from mailler.models.base import Base
from mailler.models.campaign import (
    CampaignStatus,
    EmailCampaign,
    EmailSend,
    EmailSendStatus,
)
from mailler.models.contact import Contact, ContactGroup, ContactGroupMember, ContactStatus
from mailler.models.email import Email, EmailStatus, ProviderStats
from mailler.models.template import EmailTemplate, TemplateStatus

__all__ = [
    "Base",
    "CampaignStatus",
    "Contact",
    "ContactGroup",
    "ContactGroupMember",
    "ContactStatus",
    "Email",
    "EmailCampaign",
    "EmailSend",
    "EmailSendStatus",
    "EmailStatus",
    "EmailTemplate",
    "ProviderStats",
    "TemplateStatus",
]
