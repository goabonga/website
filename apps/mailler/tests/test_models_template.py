# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for the EmailTemplate model."""

from mailler.models import Base, EmailTemplate, TemplateStatus


class TestTemplateStatus:
    """Template lifecycle statuses."""

    def test_values(self):
        assert [s.value for s in TemplateStatus] == ["draft", "active", "archived"]
        assert TemplateStatus.ACTIVE == "active"

    def test_is_string_enum(self):
        assert isinstance(TemplateStatus.ACTIVE, str)


class TestTemplateTable:
    """Table definition."""

    def test_table_registered(self):
        assert "email_templates" in Base.metadata.tables

    def test_slug_is_unique_per_client_only(self):
        table = EmailTemplate.__table__
        assert not table.columns["slug"].unique
        unique = [
            constraint
            for constraint in table.constraints
            if constraint.__class__.__name__ == "UniqueConstraint"
        ]
        assert [(c.name, [col.name for col in c.columns]) for c in unique] == [
            ("uq_email_templates_client_slug", ["client_id", "slug"])
        ]

    def test_client_is_required_and_indexed(self):
        column = EmailTemplate.__table__.columns["client_id"]
        assert column.nullable is False
        assert column.index

    def test_columns(self):
        columns = EmailTemplate.__table__.columns
        for name in (
            "client_id",
            "slug",
            "name",
            "subject_template",
            "mjml_source",
            "status",
            "variables",
        ):
            assert name in columns
