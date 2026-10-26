# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Steps for the chunked upload feature."""

from apt_server.acl.packages import Caller
from apt_server.main import app
from apt_server.services.apt_auth import resolve_caller
from behave import given, when
from debfactory import build_deb

CHUNK = 64


def set_caller(caller):
    app.dependency_overrides[resolve_caller] = lambda: caller


@given('I am the apt caller "{sub}" with scopes "{scopes}"')
@when('I am the apt caller "{sub}" with scopes "{scopes}"')
def apt_caller(context, sub, scopes):
    set_caller(Caller(sub=sub, scopes=frozenset(scopes.split())))


@given("I am an anonymous apt caller")
def anonymous_apt_caller(context):
    set_caller(None)


@when('I start a chunked upload of the package "{name}" version "{version}"')
def start_upload(context, name, version):
    context.raw = build_deb(name, version)
    context.chunks = [context.raw[i : i + CHUNK] for i in range(0, len(context.raw), CHUNK)]
    context.response = context.client.post(
        "/api/upload/init",
        json={
            "filename": f"{name}.deb",
            "total_size": len(context.raw),
            "total_chunks": len(context.chunks),
            "suite": "stable",
            "component": "main",
            "visibility": "private",
        },
    )
    if context.response.status_code == 200:
        context.upload_id = context.response.json()["upload_id"]


def send(context, indexes):
    for index in indexes:
        context.response = context.client.post(
            f"/api/upload/{context.upload_id}/chunk",
            params={"index": index},
            files={"chunk": ("chunk", context.chunks[index])},
        )


@when("I send all the chunks in order")
def send_all(context):
    send(context, range(len(context.chunks)))
    assert context.response.status_code == 200


@when("I send only the first chunk")
def send_first(context):
    send(context, [0])


@when("I complete the chunked upload")
def complete(context):
    context.response = context.client.post(f"/api/upload/{context.upload_id}/complete")
    if context.response.status_code == 200:
        context.last_package = context.response.json()


@when("I cancel the chunked upload")
def cancel(context):
    context.response = context.client.delete(f"/api/upload/{context.upload_id}")
