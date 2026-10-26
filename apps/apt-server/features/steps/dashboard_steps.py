# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Steps for the dashboard feature."""

from apt_server.acl.packages import Caller
from apt_server.db.models import Package
from apt_server.main import app
from apt_server.services.apt_auth import resolve_caller
from behave import given, then, when
from debfactory import build_deb
from sqlalchemy import select


@given('I am the signed-in user "{sub}"')
def signed_in_user(context, sub):
    caller = Caller(sub=sub, display_name=f"{sub}@example.com", is_session=True)
    app.dependency_overrides[resolve_caller] = lambda: caller


def package_id(context, name):
    async def find(session):
        return (await session.execute(select(Package.id).where(Package.name == name))).scalar_one()

    return context.run_db(find)


@when("I open the dashboard without following redirects")
def open_dashboard(context):
    context.response = context.client.get("/dashboard", follow_redirects=False)


@when('I submit the upload form with the package "{name}" version "{version}"')
def submit_upload(context, name, version):
    context.response = context.client.post(
        "/dashboard/upload",
        files={"deb": (f"{name}.deb", build_deb(name, version), "application/octet-stream")},
        data={"suite": "stable", "component": "main", "visibility": "private"},
        follow_redirects=False,
    )


@when('I share the package "{name}" with user "{user}"')
def share(context, name, user):
    context.response = context.client.post(
        f"/dashboard/{package_id(context, name)}/share",
        data={"grantee": user, "grantee_type": "user", "role": "read"},
        follow_redirects=False,
    )


@when('I delete the package "{name}" from the dashboard')
def delete(context, name):
    context.response = context.client.post(
        f"/dashboard/{package_id(context, name)}/delete", follow_redirects=False
    )


@then('the dashboard lists "{name}"')
def dashboard_lists(context, name):
    assert name in context.client.get("/dashboard").text


@then('the dashboard does not list "{name}"')
def dashboard_does_not_list(context, name):
    assert name not in context.client.get("/dashboard").text
