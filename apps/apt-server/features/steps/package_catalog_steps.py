# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Steps for the package catalog feature (SQLite database, real schema)."""

from apt_server.acl.packages import Caller, can_write, visible_package_filter
from apt_server.db.models import ACLRole, Package, PackageACL, PackageVisibility
from behave import given, then, when
from sqlalchemy import select
from sqlalchemy.orm import selectinload


def make_package(name, owner, visibility):
    return Package(
        name=name,
        version="1.0",
        architecture="amd64",
        suite="stable",
        component="main",
        owner_id=owner,
        visibility=PackageVisibility(visibility),
        filename=f"pool/main/{name[0]}/{name}/{name}_1.0_amd64.deb",
        size=1,
        md5="0" * 32,
        sha1="1" * 40,
        sha256="2" * 64,
    )


@given("a catalog with these packages")
def seed_catalog(context):
    async def seed(session):
        session.add_all(
            [make_package(r["name"], r["owner"], r["visibility"]) for r in context.table]
        )
        await session.commit()

    context.run_db(seed)


def add_grant(context, owner, role, name, **grantee):
    async def grant(session):
        package = (await session.execute(select(Package).where(Package.name == name))).scalar_one()
        assert package.owner_id == owner
        session.add(
            PackageACL(package_id=package.id, role=ACLRole(role), granted_by=owner, **grantee)
        )
        await session.commit()

    context.run_db(grant)


@given('"{owner}" grants "{role}" on "{name}" to user "{user}"')
def grant_user(context, owner, role, name, user):
    add_grant(context, owner, role, name, grantee_user_id=user)


@given('"{owner}" grants "{role}" on "{name}" to group "{group}"')
def grant_group(context, owner, role, name, group):
    add_grant(context, owner, role, name, grantee_group=group)


def list_visible(context, caller):
    async def query(session):
        rows = await session.execute(select(Package.name).where(visible_package_filter(caller)))
        return sorted(rows.scalars())

    context.visible = context.run_db(query)


@when("an anonymous caller lists the visible packages")
def anonymous_lists(context):
    list_visible(context, None)


@when('the caller "{sub}" lists the visible packages')
def caller_lists(context, sub):
    list_visible(context, Caller(sub=sub))


@when('the user "{sub}" with mailbox "{email}" lists the visible packages')
def caller_with_email_lists(context, sub, email):
    list_visible(context, Caller(sub=sub, display_name=email))


@when('the member "{sub}" of group "{group}" lists the visible packages')
def caller_in_group_lists(context, sub, group):
    list_visible(context, Caller(sub=sub, groups=frozenset({group})))


@when("an administrator lists the visible packages")
def admin_lists(context):
    list_visible(context, Caller(sub="root", scopes=frozenset({"apt:admin"})))


@then('the visible packages are "{names}"')
def check_visible(context, names):
    assert context.visible == sorted(names.split(",")), context.visible


def writable(context, caller, name):
    async def query(session):
        stmt = select(Package).where(Package.name == name).options(selectinload(Package.acl))
        return can_write(caller, (await session.execute(stmt)).scalar_one())

    return context.run_db(query)


@then('caller "{sub}" can write "{name}"')
def can_write_step(context, sub, name):
    assert writable(context, Caller(sub=sub), name)


@then('caller "{sub}" cannot write "{name}"')
def cannot_write_step(context, sub, name):
    assert not writable(context, Caller(sub=sub), name)


@then('an anonymous caller cannot write "{name}"')
def anonymous_cannot_write(context, name):
    assert not writable(context, None, name)
