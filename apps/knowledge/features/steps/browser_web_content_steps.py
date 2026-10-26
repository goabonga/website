# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Steps for the collection and document pages in a browser.

The documents are embedded by the deterministic embedding model of the stack, and stored in
the SQLite stand-in: the scenarios read the database back to check what the pages saved.
"""

from unittest.mock import patch

import browser_stack
from behave import given, then, when
from fakes import FakeEmbeddingService, hashing_vectorizer

from knowledge.config import get_settings
from knowledge.models import Collection, Organization


@browser_stack.scenario_setup
def install_embedding_model(stack, scenario):
    dimension = get_settings().embedding_dimension
    stack.embedder = FakeEmbeddingService(
        dimension, lambda text: hashing_vectorizer(text, dimension)
    )
    for target in (
        "knowledge.services.documents.get_embedding_service",
        "knowledge.routes.web.documents.get_embedding_service",
    ):
        scenario.enter_context(patch(target, lambda: stack.embedder))


def _collection(context, name):
    with context.stack.db.session() as session:
        return session.query(Collection).filter(Collection.name == name).one()


# --- forms ---------------------------------------------------------------------------------


@given("the browser accepts the confirmation dialogs")
def step_accept_dialogs(context):
    context.page.on("dialog", lambda dialog: dialog.accept())


@when('I open the new document form of "{name}"')
def step_new_document_form(context, name):
    context.page.goto(f"/documents/{_collection(context, name).id}/new")


@when('I choose the file "{filename}" containing "{text}" in the upload field')
def step_upload(context, filename, text):
    context.page.get_by_label("Upload File").set_input_files(
        {"name": filename, "mimeType": "text/plain", "buffer": text.encode()}
    )


@when('I select the documents "{first}" and "{second}"')
def step_select_documents(context, first, second):
    for text in (first, second):
        row = context.page.locator("tr", has_text=text)
        row.locator("input.document-checkbox").check()


@when('I open the collection "{name}" of the workspace "{workspace}"')
def step_open_foreign_collection(context, name, workspace):
    context.page.goto(f"/collections/{_collection(context, name).id}")


# --- what was saved --------------------------------------------------------------------------


@then('the workspace "{workspace}" should hold the collection "{name}"')
def step_holds_collection(context, workspace, name):
    with context.stack.db.session() as session:
        organization = session.query(Organization).filter(Organization.name == workspace).one()
        names = [
            c.name
            for c in session.query(Collection).filter(Collection.organization_id == organization.id)
        ]
    assert name in names, names


@then('the workspace "{workspace}" should hold {count:d} collections')
def step_collection_count(context, workspace, count):
    with context.stack.db.session() as session:
        organization = session.query(Organization).filter(Organization.name == workspace).one()
        total = (
            session.query(Collection).filter(Collection.organization_id == organization.id).count()
        )
    assert total == count, total


@then('the embedding model embedded "{text}"')
def step_embedded(context, text):
    embedded = [t for call in context.stack.embedder.calls for t in call]
    assert text in embedded, embedded
