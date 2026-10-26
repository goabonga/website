# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Steps for the package API feature."""

from apt_server.auth.dependencies import AuthContext, get_auth_context
from apt_server.auth.models import User
from apt_server.main import app
from behave import given, then, when
from debfactory import build_deb


@given('I am logged in as "{sub}" with scopes "{scopes}"')
def log_in(context, sub, scopes):
    user = User(id=sub, scopes=scopes.split())
    app.dependency_overrides[get_auth_context] = lambda: AuthContext(user)


def upload(context, content, component, visibility="private"):
    context.response = context.client.post(
        "/api/packages",
        files={"deb": ("package.deb", content, "application/octet-stream")},
        data={"suite": "stable", "component": component, "visibility": visibility},
    )
    if context.response.status_code == 201:
        context.last_package = context.response.json()


@when('I upload the package "{name}" version "{version}" to component "{component}"')
@given('I uploaded the package "{name}" version "{version}" to component "{component}"')
def upload_package(context, name, version, component):
    upload(context, build_deb(name, version, "amd64"), component)


@when("I upload a file that is not a Debian package")
def upload_garbage(context):
    upload(context, b"definitely not a deb", "main")


@when("I list the packages")
def list_packages(context):
    context.response = context.client.get("/api/packages")


@when('I grant "{role}" on the last package to user "{user}"')
def grant(context, role, user):
    context.response = context.client.post(
        f"/api/packages/{context.last_package['id']}/acl",
        json={"grantee_user_id": user, "role": role},
    )


@when('I set the visibility of the last package to "{visibility}"')
def set_visibility(context, visibility):
    context.response = context.client.patch(
        f"/api/packages/{context.last_package['id']}", json={"visibility": visibility}
    )


@when("I delete the last package")
def delete_last(context):
    context.response = context.client.delete(f"/api/packages/{context.last_package['id']}")


@when("I trigger a reindex")
def reindex(context):
    context.response = context.client.post("/api/reindex")


@then("the response lists {count:d} package")
@then("the response lists {count:d} packages")
def lists_count(context, count):
    assert len(context.response.json()) == count, context.response.text


@then("the package file exists in the pool")
def file_exists(context):
    assert (context.repo_root / context.last_package["filename"]).is_file()


@then("the package file no longer exists in the pool")
def file_gone(context):
    assert not (context.repo_root / context.last_package["filename"]).exists()
