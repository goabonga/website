# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Behave environment used by the hook tests: the toy site, wired like an application."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from e2e_support import behave_hooks as e2e  # noqa: E402
from toy_site import site  # noqa: E402


def before_all(context):
    e2e.before_all(context)


def before_tag(context, tag):
    e2e.before_tag(context, tag)


def before_scenario(context, scenario):
    e2e.before_scenario(
        context, scenario, base_url=lambda: e2e.live_server(context, "site", site).url
    )


def after_scenario(context, scenario):
    e2e.after_scenario(context, scenario)


def after_all(context):
    e2e.after_all(context)
