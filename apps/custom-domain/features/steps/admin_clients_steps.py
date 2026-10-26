# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Steps for the authorized client administration feature."""

from behave import given, then
from custom_domain.models import AuthorizedClient


@given('an authorized client "{client_id}" exists')
def step_client_exists(context, client_id):
    with context.db.session() as session:
        client = AuthorizedClient(
            client_id=client_id,
            name=client_id.title(),
            default_upstream_target=f"/run/{client_id}.sock",
            default_cname_target="apps.example.com",
            is_active=True,
        )
        session.add(client)
        session.commit()
        context.ids[("client", client_id)] = client.id


@then("the first client has the domain count {count:d}")
def step_first_client_count(context, count):
    assert context.response.json()["items"][0]["domains_count"] == count
