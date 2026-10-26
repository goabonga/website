# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Step definitions for knowledge_base.feature."""

from unittest.mock import patch

import asterisk.knowledge_base as kb_module
from asterisk.config import config
from asterisk.knowledge_base import KnowledgeBase, close_knowledge_base, get_knowledge_base
from behave import given, then, when
from fakes import FakePostgres, install_fake_knowledge_backends


def _install(context, database):
    context.database = database
    patchers = install_fake_knowledge_backends(database)
    for patcher in patchers:
        context.add_cleanup(patcher.stop)
    kb_module._knowledge_base = None
    context.add_cleanup(setattr, kb_module, "_knowledge_base", None)


def _new_knowledge_base(max_results=3):
    return KnowledgeBase(
        database_url="postgresql://fake/fake",
        openai_api_key="sk-test",
        similarity_threshold=0.7,
        max_results=max_results,
    )


def _populate(context, table):
    for row in table:
        context.run(context.kb.add_entry(row["question"], row["answer"]))


@given("a fake database without the knowledge_base table")
def step_no_table(context):
    _install(context, FakePostgres(table_exists=False))
    context.kb = _new_knowledge_base()


@given("a fake database that already has the knowledge_base table")
def step_existing_table(context):
    _install(context, FakePostgres(table_exists=True))
    context.kb = _new_knowledge_base()


@given("a connected knowledge base")
def step_connected(context):
    _install(context, FakePostgres(table_exists=True))
    context.kb = _new_knowledge_base()
    context.run(context.kb.connect())


@given("a connected knowledge base with the entries:")
def step_connected_with_entries(context):
    step_connected(context)
    _populate(context, context.table)


@given("a connected knowledge base limited to {limit:d} result with the entries:")
def step_connected_limited(context, limit):
    _install(context, FakePostgres(table_exists=True))
    context.kb = _new_knowledge_base(max_results=limit)
    context.run(context.kb.connect())
    _populate(context, context.table)


@given("a knowledge base that is not connected")
def step_not_connected(context):
    _install(context, FakePostgres(table_exists=True))
    context.kb = _new_knowledge_base()


@given("RAG is disabled")
def step_rag_disabled(context):
    _install(context, FakePostgres(table_exists=True))
    patcher = patch.object(config, "RAG_ENABLED", False)
    patcher.start()
    context.add_cleanup(patcher.stop)


@given("RAG is enabled with a fake database")
def step_rag_enabled(context):
    _install(context, FakePostgres(table_exists=True))
    for name, value in (
        ("RAG_ENABLED", True),
        ("DATABASE_URL", "postgresql://fake/fake"),
        ("OPENAI_API_KEY", "sk-test"),
    ):
        patcher = patch.object(config, name, value)
        patcher.start()
        context.add_cleanup(patcher.stop)


@when("the knowledge base connects")
def step_connect(context):
    context.run(context.kb.connect())


@when('I add the entry "{question}" answered "{answer}"')
def step_add(context, question, answer):
    context.run(context.kb.add_entry(question, answer))


@when('I search for "{query}"')
def step_search(context, query):
    context.results = context.run(context.kb.search(query))


@when('I update the first entry to "{question}" answered "{answer}"')
def step_update(context, question, answer):
    entry_id = context.database.rows[0]["id"]
    context.run(context.kb.update_entry(entry_id, question, answer))


@when("I delete the first entry")
def step_delete(context):
    context.run(context.kb.delete_entry(context.database.rows[0]["id"]))


@when("I request {limit:d} sample questions")
def step_samples(context, limit):
    context.samples = context.run(context.kb.get_sample_questions(limit=limit))


@when("the shared knowledge base is requested twice")
def step_shared_twice(context):
    context.shared = [context.run(get_knowledge_base()), context.run(get_knowledge_base())]


@when("the shared knowledge base is closed")
def step_shared_close(context):
    context.run(close_knowledge_base())


@then("the vector extension, the table and the index should have been created")
def step_schema_created(context):
    assert context.database.extension_created
    assert context.database.table_exists
    assert context.database.index_created


@then("no schema statement should have been run")
def step_no_schema(context):
    assert not context.database.extension_created
    assert not context.database.index_created


@then("the database should hold {count:d} entry")
@then("the database should hold {count:d} entries")
def step_row_count(context, count):
    assert len(context.database.rows) == count


@then("the entry should have an embedding")
def step_has_embedding(context):
    assert context.database.rows[0]["embedding"].startswith("[")


@then('the first result should be "{question}"')
def step_first_result(context, question):
    assert context.results[0].question == question


@then("every result should have a similarity of at least {minimum:f}")
def step_similarity(context, minimum):
    assert context.results
    assert all(entry.similarity >= minimum for entry in context.results)


@then("I should receive no result")
def step_no_result(context):
    assert context.results == []


@then("I should receive {count:d} result")
def step_n_results(context, count):
    assert len(context.results) == count


@then('the first entry should read "{question}" answered "{answer}"')
def step_entry_values(context, question, answer):
    row = context.database.rows[0]
    assert (row["question"], row["answer"]) == (question, answer)


@then("I should receive {count:d} sample questions")
def step_sample_count(context, count):
    assert len(context.samples) == count


@then("there should be no shared knowledge base")
def step_no_shared(context):
    assert context.run(get_knowledge_base()) is None


@then("both requests should return the same connected instance")
def step_same_instance(context):
    first, second = context.shared
    assert first is second
    assert first.pool is context.database


@then("the database connection should be closed")
def step_db_closed(context):
    assert context.database.closed
