# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Database models for Mailler."""

from mailler.models.base import Base
from mailler.models.contact import Contact, ContactGroup, ContactGroupMember, ContactStatus
from mailler.models.email import Email, EmailStatus, ProviderStats
from mailler.models.template import EmailTemplate, TemplateStatus

__all__ = [
    "Base",
    "Contact",
    "ContactGroup",
    "ContactGroupMember",
    "ContactStatus",
    "Email",
    "EmailStatus",
    "EmailTemplate",
    "ProviderStats",
    "TemplateStatus",
]
