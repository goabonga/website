# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Steps for the APT index rendering feature."""

import gzip

from apt_server.acl.packages import Caller
from apt_server.config import settings
from apt_server.db.models import Package, PackageVisibility
from apt_server.services import indexes
from behave import given, then, when


def make_package(name, owner, visibility, component):
    return Package(
        name=name,
        version="1.0",
        architecture="amd64",
        suite="stable",
        component=component,
        owner_id=owner,
        visibility=PackageVisibility(visibility),
        filename=f"pool/{component}/{name[0]}/{name}/{name}_1.0_amd64.deb",
        size=42,
        md5="0" * 32,
        sha1="1" * 40,
        sha256="2" * 64,
        control={"Package": name, "Version": "1.0", "Architecture": "amd64"},
    )


@given('the repository serves components "{names}" of which "{public}" is public')
def configure_repository(context, names, public):
    context.patch(settings, "apt_components", names)
    context.patch(settings, "apt_public_components", public)
    context.patch(settings, "apt_architectures", "amd64")
    context.patch(settings, "apt_suites", "stable")


@given("a catalog with these indexed packages")
def seed_catalog(context):
    async def seed(session):
        session.add_all(
            [
                make_package(r["name"], r["owner"], r["visibility"], r["component"])
                for r in context.table
            ]
        )
        await session.commit()

    context.run_db(seed)


def fetch_index(context, caller, component):
    async def render(session):
        plain = await indexes.render_packages(
            session, caller, suite="stable", component=component, architecture="amd64"
        )
        zipped = await indexes.render_packages(
            session, caller, suite="stable", component=component, architecture="amd64", gzip=True
        )
        return plain, zipped

    context.plain_index, context.gzip_index = context.run_db(render)
    context.index_text = context.plain_index.decode()


@when('an anonymous caller fetches the "{component}" Packages index')
@given('an anonymous caller fetched the "{component}" Packages index')
def anonymous_fetches_index(context, component):
    fetch_index(context, None, component)


@when('the caller "{sub}" fetches the "{component}" Packages index')
def caller_fetches_index(context, sub, component):
    fetch_index(context, Caller(sub=sub), component)


@when('a public package "{name}" is added to the catalog')
def add_public_package(context, name):
    async def add(session):
        session.add(make_package(name, "alice", "public", "main"))
        await session.commit()

    context.run_db(add)


@when("the cached indexes are invalidated")
def invalidate_cache(context):
    async def invalidate(session):
        await indexes.invalidate_index_cache(session)
        await session.commit()

    context.run_db(invalidate)


@then('the index lists "{name}"')
def index_lists(context, name):
    assert f"Package: {name}\n" in context.index_text, context.index_text


@then('the index does not list "{name}"')
def index_does_not_list(context, name):
    assert f"Package: {name}\n" not in context.index_text


@then('the index entry for "{name}" has "{line}"')
def index_entry_has(context, name, line):
    stanza = next(s for s in context.index_text.split("\n\n") if f"Package: {name}\n" in s)
    assert line in stanza.splitlines(), stanza


@then('the index entry for "{name}" has a "{field}" checksum')
def index_entry_has_checksum(context, name, field):
    stanza = next(s for s in context.index_text.split("\n\n") if f"Package: {name}\n" in s)
    assert any(line.startswith(f"{field}: ") and len(line) > 20 for line in stanza.splitlines())


@then("the compressed index decompresses to the same content")
def gzip_matches(context):
    assert gzip.decompress(context.gzip_index) == context.plain_index


def fetch_release(context, caller):
    async def render(session):
        return await indexes.render_release(session, caller, suite="stable")

    context.release_text = context.run_db(render).decode()


@when("an anonymous caller fetches the Release file")
def anonymous_fetches_release(context):
    fetch_release(context, None)


@when('the caller "{sub}" fetches the Release file')
def caller_fetches_release(context, sub):
    fetch_release(context, Caller(sub=sub))


@then('the Release lists component "{component}"')
def release_lists_component(context, component):
    components = next(
        line for line in context.release_text.splitlines() if line.startswith("Components:")
    )
    assert component in components.split()[1:], components


@then('the Release does not mention "{text}"')
def release_does_not_mention(context, text):
    assert text not in context.release_text


@then('the Release references "{path}"')
def release_references(context, path):
    assert path in context.release_text
