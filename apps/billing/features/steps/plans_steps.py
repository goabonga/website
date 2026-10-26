# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Step definitions for the public plans."""

import json
from unittest.mock import patch

from behave import given, then
from billing.config import settings


def _run(context, coro):
    return context.loop.run_until_complete(coro)


@given("the plans are public")
def step_plans_public(context):
    """Serve the plans without a token for the scenario (PLANS_PUBLIC=true)."""
    patcher = patch.object(settings, "plans_public", True)
    patcher.start()
    context.add_cleanup(patcher.stop)


@given('a SaaS app "{name}" with slug "{slug}" has a plan "{plan}" with the limits \'{limits}\'')
def step_saas_with_plan_limits(context, name, slug, plan, limits):
    """Create a SaaS app with one plan whose limits are an arbitrary JSON document."""
    response = _run(
        context, context.client.post("/platform/saas", json={"name": name, "slug": slug})
    )
    assert response.status_code == 201, response.text
    saas_id = response.json()["id"]
    context.created_ids["saas_id"] = saas_id

    response = _run(
        context,
        context.client.post(
            f"/platform/{saas_id}/products",
            json={"name": plan.title(), "slug": plan, "metadata": {"limits": json.loads(limits)}},
        ),
    )
    assert response.status_code == 201, response.text


@then("the limits of the plan \"{plan}\" should be '{limits}'")
def step_check_plan_limits(context, plan, limits):
    plans = {entry["slug"]: entry for entry in context.response.json()["plans"]}
    assert plans[plan]["limits"] == json.loads(limits), plans[plan]["limits"]
