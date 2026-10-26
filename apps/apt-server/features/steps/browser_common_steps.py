# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Steps shared by the browser scenarios: users, catalog, sign-in, status."""

import browser_support
from apt_server.db.models import Package, PackageVisibility
from behave import given, step, then
from e2e_support import steps  # noqa: F401
from e2e_support.steps import current_page


def user_id(context, email):
    """The id the identity provider gave to ``email``, or ``email`` for an unknown user."""
    user = browser_support.provider_of(context).user_by_email(email)
    return user.id if user else email


@given("the identity provider knows these users")
def provider_users(context):
    from e2e_support.oidc import User

    provider = browser_support.provider_of(context)
    for row in context.table:
        provider.add_user(User(email=row["email"], name=row["name"], password=row["password"]))
    context.passwords = {row["email"]: row["password"] for row in context.table}


@given("the browser catalog has these packages")
def browser_catalog(context):
    def package(row):
        name, component = row["name"], row["component"]
        return Package(
            name=name,
            version="1.0",
            architecture="amd64",
            suite="stable",
            component=component,
            owner_id=user_id(context, row["owner"]),
            visibility=PackageVisibility(row["visibility"]),
            filename=f"pool/{component}/{name[0]}/{name}/{name}_1.0_amd64.deb",
            size=42,
            md5="0" * 32,
            sha1="1" * 40,
            sha256="2" * 64,
            control={"Package": name, "Version": "1.0", "Architecture": "amd64"},
        )

    async def seed(session):
        session.add_all([package(row) for row in context.table])
        await session.commit()

    context.run_db(seed)


@step('I sign in as "{email}"')
def sign_in(context, email):
    page = current_page(context)
    page.goto("/login")
    page.get_by_label("Email").fill(email)
    page.get_by_label("Password").fill(context.passwords[email])
    page.get_by_role("button", name="Sign in").click()
    page.wait_for_url(f"{context.base_url}/**")


@step('I visit "{path}"')
def visit(context, path):
    context.visit = current_page(context).goto(path)


@then("the page answers {status:d}")
def page_answers(context, status):
    assert context.visit.status == status, f"expected {status}, got {context.visit.status}"
