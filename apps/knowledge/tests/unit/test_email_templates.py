# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for the MJML templates shipped for the mailler service."""

import json
import re
import subprocess
import sys

import pytest

from knowledge import email_templates
from knowledge.email_templates import TEMPLATES_DIR, template_slugs

# What `mailler templates import` accepts in a description
DESCRIPTION_KEYS = {
    "name",
    "description",
    "subject_template",
    "plain_text",
    "variables",
    "metadata",
    "status",
}
PLACEHOLDER = re.compile(r"\{\{\s*(\w+)\s*\}\}")

SLUGS = [
    "workspace_deleted",
    "workspace_deletion",
    "workspace_deletion_reminder",
    "workspace_deletion_scheduled",
    "workspace_invitation",
]


def test_the_five_templates_are_shipped():
    assert template_slugs() == SLUGS


def test_the_constants_name_the_shipped_templates():
    constants = {
        email_templates.WORKSPACE_INVITATION,
        email_templates.WORKSPACE_DELETION,
        email_templates.WORKSPACE_DELETION_REMINDER,
        email_templates.WORKSPACE_DELETION_SCHEDULED,
        email_templates.WORKSPACE_DELETED,
    }
    assert constants == set(SLUGS)


@pytest.mark.parametrize("slug", SLUGS)
class TestTemplateFiles:
    def test_description_is_valid_for_mailler(self, slug):
        description = json.loads((TEMPLATES_DIR / f"{slug}.json").read_text())
        assert set(description) <= DESCRIPTION_KEYS
        assert description["subject_template"]
        assert description["name"]

    def test_slug_is_valid_for_mailler(self, slug):
        assert re.fullmatch(r"[a-z0-9]+(?:[-_][a-z0-9]+)*", slug) and len(slug) <= 100

    def test_source_is_mjml_with_jinja_placeholders(self, slug):
        source = (TEMPLATES_DIR / f"{slug}.mjml").read_text()
        assert source.lstrip().startswith("<mjml>")
        assert PLACEHOLDER.search(source)
        # the old %variable% syntax is not understood by mailler in the HTML
        assert not re.search(r"%[A-Za-z_]\w*%", source)

    def test_variables_are_all_footers_or_content_we_send(self, slug):
        source = (TEMPLATES_DIR / f"{slug}.mjml").read_text()
        subject = json.loads((TEMPLATES_DIR / f"{slug}.json").read_text())["subject_template"]
        used = set(PLACEHOLDER.findall(source)) | set(PLACEHOLDER.findall(subject))
        assert {"workspace_name", "user_email", "year"} <= used


def test_every_description_has_its_source():
    sources = {path.stem for path in TEMPLATES_DIR.glob("*.mjml")}
    descriptions = {path.stem for path in TEMPLATES_DIR.glob("*.json")}
    assert sources == descriptions


def test_module_prints_the_directory_for_the_import_command():
    output = subprocess.run(
        [sys.executable, "-m", "knowledge.email_templates"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    assert output.strip() == str(TEMPLATES_DIR)
