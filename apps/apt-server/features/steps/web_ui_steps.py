# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Steps for the public web pages feature."""

from apt_server.db.models import Package
from behave import when
from sqlalchemy import select


@when('I open the detail page of package "{name}"')
def open_detail(context, name):
    async def find(session):
        return (await session.execute(select(Package.id).where(Package.name == name))).scalar_one()

    package_id = context.run_db(find)
    context.response = context.client.get(f"/packages/{package_id}")
