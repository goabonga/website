# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Step definitions for the signing keys feature."""

import asyncio

from auth.api.deps import get_jwks_service
from auth.core.security import AESEncryption, hash_password, verify_password
from auth.db.models.jwk import JWK
from behave import given, then, when
from cryptography.exceptions import InvalidTag
from helpers import fresh_encryption_key
from sqlalchemy import select
from sqlite_db import use_database


def _stored_keys(context):
    """The JWK rows currently stored."""
    return list(context.database.sync_session.scalars(select(JWK)))


@given("a signing key store protected by a fresh encryption key")
def step_key_store(context):
    use_database(context)
    context.encryption = fresh_encryption_key(context)
    context.jwks_service = get_jwks_service()


def _remember(context, key):
    context.kids = getattr(context, "kids", []) + [key.kid]


@given("the operator generated and activated a signing key")
@when("the operator generates and activates a signing key")
def step_generate_active(context):
    _remember(context, asyncio.run(context.jwks_service.generate_key(context.db, activate=True)))


@when("the operator generates a signing key without activating it")
def step_generate_inactive(context):
    _remember(context, asyncio.run(context.jwks_service.generate_key(context.db, activate=False)))


@given("the operator rotates the keys")
@when("the operator rotates the keys")
def step_rotate(context):
    _remember(context, asyncio.run(context.jwks_service.rotate_keys(context.db)))


@when("the operator revokes the first key")
def step_revoke_first(context):
    asyncio.run(context.jwks_service.revoke_key(context.db, context.kids[0]))


@then("the JWKS document lists {count:d} key")
@then("the JWKS document lists {count:d} keys")
def step_key_count(context, count):
    keys = context.response.json()["keys"]
    assert len(keys) == count, keys


@then("the published key is an RS256 signature key")
def step_published_key(context):
    key = context.response.json()["keys"][0]
    assert (key["kty"], key["alg"], key["use"]) == ("RSA", "RS256", "sig"), key
    assert key["n"] and key["e"]


@then("the published keys expose no private material")
def step_no_private_material(context):
    for key in context.response.json()["keys"]:
        assert not {"d", "p", "q", "dp", "dq", "qi"} & set(key), key


@then("no key is active")
def step_no_active(context):
    assert not any(row.is_active for row in _stored_keys(context))


@then("exactly one key is active")
def step_one_active(context):
    assert sum(row.is_active for row in _stored_keys(context)) == 1


@then("the published key is the active key")
def step_published_is_active(context):
    active = next(row for row in _stored_keys(context) if row.is_active)
    assert [k["kid"] for k in context.response.json()["keys"]] == [active.kid]


@then("the stored private key is not a PEM document")
def step_not_pem(context):
    assert b"BEGIN" not in _stored_keys(context)[0].private_key_encrypted


@then("the stored private key can be decrypted with the encryption key")
def step_decrypts(context):
    private = context.jwks_service.decrypt_private_key(_stored_keys(context)[0])
    assert private.key_size == 2048


@then("the stored private key cannot be decrypted with another key")
def step_other_key_fails(context):
    other = AESEncryption(AESEncryption.generate_key())
    try:
        other.decrypt(_stored_keys(context)[0].private_key_encrypted)
    except InvalidTag:
        return
    raise AssertionError("decryption with another key unexpectedly succeeded")


@when('the password "{password}" is hashed')
def step_hash(context, password):
    context.password_hash = hash_password(password)


@then('the hash starts with "{prefix}"')
def step_hash_prefix(context, prefix):
    assert context.password_hash.startswith(prefix)


@then('the password "{password}" matches the hash')
def step_password_matches(context, password):
    assert verify_password(password, context.password_hash)


@then('the password "{password}" does not match the hash')
def step_password_differs(context, password):
    assert not verify_password(password, context.password_hash)
