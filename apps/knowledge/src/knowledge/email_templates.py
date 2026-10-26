# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""The email templates of the application.

The emails are rendered by the mailler service, not by this application: the MJML
sources live here, next to the code that sends them, and are imported into mailler for
the OAuth2 client of the application. Each template is two files named after its slug:

* ``<slug>.mjml``: the MJML source, with ``{{ variable }}`` placeholders;
* ``<slug>.json``: its description for mailler (``name``, ``description`` and the
  ``subject_template``).

``mailler templates import --client-id <client> "$(python -m knowledge.email_templates)"``
imports the directory, and can be run again at every deployment.
"""

from pathlib import Path

TEMPLATES_DIR = Path(__file__).resolve().parent / "templates" / "emails"

WORKSPACE_INVITATION = "workspace_invitation"
WORKSPACE_DELETION = "workspace_deletion"
WORKSPACE_DELETION_REMINDER = "workspace_deletion_reminder"
WORKSPACE_DELETION_SCHEDULED = "workspace_deletion_scheduled"
WORKSPACE_DELETED = "workspace_deleted"


def template_slugs() -> list[str]:
    """Return the slugs of the shipped templates, sorted."""
    return sorted(source.stem for source in TEMPLATES_DIR.glob("*.mjml"))


if __name__ == "__main__":
    print(TEMPLATES_DIR)
