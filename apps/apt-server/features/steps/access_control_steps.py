# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Steps for the access control feature (rules evaluated in-process)."""

from apt_server.acl import components, scopes
from apt_server.config import settings
from behave import given, then


@given('the repository serves components "{names}"')
def serve_components(context, names):
    context.patch(settings, "apt_components", names)


@given('the public components are "{names}"')
def public_components(context, names):
    context.patch(settings, "apt_public_components", names)


@given('a caller with scopes "{raw}"')
def caller_scopes(context, raw):
    context.scopes = scopes.parse_scopes(raw)


@then('component "{name}" is public')
def component_public(context, name):
    assert components.is_known_component(name)
    assert components.is_public_component(name)


@then('component "{name}" is known but not public')
def component_private(context, name):
    assert components.is_known_component(name)
    assert not components.is_public_component(name)


@then('component "{name}" is unknown')
def component_unknown(context, name):
    assert not components.is_known_component(name)


@then("the caller may read")
def may_read(context):
    assert scopes.may_read(context.scopes)


@then("the caller may not read")
def may_not_read(context):
    assert not scopes.may_read(context.scopes)


@then('the caller may write to component "{name}"')
def may_write(context, name):
    assert scopes.may_write(context.scopes, name)


@then('the caller may not write to component "{name}"')
def may_not_write(context, name):
    assert not scopes.may_write(context.scopes, name)


@then("the caller may reindex")
def may_reindex(context):
    assert scopes.may_reindex(context.scopes)


@then("the caller may not reindex")
def may_not_reindex(context):
    assert not scopes.may_reindex(context.scopes)
