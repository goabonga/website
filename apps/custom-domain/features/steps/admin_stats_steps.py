# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Steps for the administration statistics feature."""

from behave import then


@then("the overview reports {domains:d} domains, {clients:d} clients and {templates:d} templates")
def step_overview_totals(context, domains, clients, templates):
    body = context.response.json()
    assert (body["domains"]["total"], body["clients"]["total"], body["templates"]["total"]) == (
        domains,
        clients,
        templates,
    ), body


@then("the overview counts these domains")
def step_overview_counters(context):
    domains = context.response.json()["domains"]
    for row in context.table:
        assert domains[row["counter"]] == int(row["value"]), (row["counter"], domains)


@then('the JSON object "{name}" has "{field}" equal to {value:d}')
def step_object_field(context, name, field, value):
    assert context.response.json()[name][field] == value


@then('the top clients are "{names}"')
def step_top_clients(context, names):
    assert [c["client_id"] for c in context.response.json()] == [
        n.strip() for n in names.split(",")
    ]


@then("the JSON list has {count:d} items")
def step_list_items(context, count):
    assert len(context.response.json()) == count


@then("the dashboard has an overview, {top:d} top clients and {recent:d} recent activities")
def step_dashboard(context, top, recent):
    body = context.response.json()
    assert body["overview"]["domains"]["total"] == 1
    assert len(body["top_clients"]) == top
    assert len(body["recent_activity"]) == recent
