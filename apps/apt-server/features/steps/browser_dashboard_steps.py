# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Steps for the package dashboard browser scenarios."""

import math
import os
from pathlib import Path

import browser_support
from apt_server.config import settings
from behave import given, step, then
from debfactory import build_deb
from e2e_support.steps import current_page


@given("the upload chunk size is {size:d} bytes")
def chunk_size(context, size):
    context.patch(settings, "upload_chunk_size", size)


def write_file(context, name, content):
    path = Path(context.workdir) / name
    path.write_bytes(content)
    return path


@step('I choose the package file "{name}" version "{version}" of {size:d} bytes')
def choose_package(context, name, version, size):
    deb = build_deb(name, version, description=os.urandom(size).hex())
    context.deb_size = len(deb)
    path = write_file(context, f"{name}_{version}_amd64.deb", deb)
    page = current_page(context)
    context.chunk_requests = []
    page.on(
        "request",
        lambda request: "/chunk?" in request.url and context.chunk_requests.append(request.url),
    )
    page.get_by_label(".deb file").set_input_files(str(path))


@step('I choose a file "{name}" that is not a package')
def choose_garbage(context, name):
    path = write_file(context, name, b"this is not an ar archive")
    current_page(context).get_by_label(".deb file").set_input_files(str(path))


@then("the file was sent in as many chunks as the chunk size requires")
def chunks_sent(context):
    expected = math.ceil(context.deb_size / settings.upload_chunk_size)
    assert expected > 1, "the scenario should use several chunks"
    assert len(context.chunk_requests) == expected, (
        f"{len(context.chunk_requests)} chunks sent, {expected} expected"
    )


@step('the next confirmation dialog is accepted and says "{message}"')
def accept_confirmation(context, message):
    context.dialogs = []

    def handle(dialog):
        context.dialogs.append(dialog.message)
        dialog.accept()

    current_page(context).once("dialog", handle)


@step("the next confirmation dialog is dismissed")
def dismiss_confirmation(context):
    context.dialogs = []

    def handle(dialog):
        context.dialogs.append(dialog.message)
        dialog.dismiss()

    current_page(context).once("dialog", handle)


@then('the confirmation asked "{message}"')
def confirmation_asked(context, message):
    assert context.dialogs == [message], f"the page asked {context.dialogs}"


@step('I visit the share page of the package "{name}"')
def visit_share(context, name):
    context.visit = current_page(context).goto(
        f"/dashboard/{browser_support.package_id(context, name)}/share"
    )


@step("I start from a browser without cookies")
def forget_cookies(context):
    context.browser_context.clear_cookies()
