# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Local cache of user profiles."""

from apt_server.db.models import UserCache
from apt_server.services import user_cache


async def test_upsert_inserts_a_new_profile(db) -> None:
    await user_cache.upsert(db, sub="s1", email="a@example.com", name="Alice", avatar_url="/a.png")

    row = await db.get(UserCache, "s1")
    assert (row.email, row.name, row.avatar_url) == ("a@example.com", "Alice", "/a.png")
    assert row.updated_at is not None


async def test_upsert_updates_an_existing_profile(db) -> None:
    await user_cache.upsert(db, sub="s1", email="a@example.com", name="Alice")

    await user_cache.upsert(db, sub="s1", email="new@example.com", name="Alice B")

    row = await db.get(UserCache, "s1")
    assert (row.email, row.name) == ("new@example.com", "Alice B")


async def test_upsert_keeps_existing_values_when_new_ones_are_blank(db) -> None:
    await user_cache.upsert(db, sub="s1", email="a@example.com", name="Alice", avatar_url="/a.png")

    await user_cache.upsert(db, sub="s1", email="", name="", avatar_url="")

    row = await db.get(UserCache, "s1")
    assert (row.email, row.name, row.avatar_url) == ("a@example.com", "Alice", "/a.png")


async def test_resolve_display_by_sub_or_email(db) -> None:
    await user_cache.upsert(db, sub="s1", email="a@example.com", name="Alice")

    assert await user_cache.resolve_display(db, "s1") == "a@example.com"
    assert await user_cache.resolve_display(db, "a@example.com") == "a@example.com"


async def test_resolve_display_falls_back_to_the_identifier(db) -> None:
    assert await user_cache.resolve_display(db, "unknown") == "unknown"


async def test_resolve_many_maps_every_identifier(db) -> None:
    await user_cache.upsert(db, sub="s1", email="a@example.com")
    await user_cache.upsert(db, sub="s2", email="b@example.com")

    result = await user_cache.resolve_many(db, ["s1", "b@example.com", "ghost"])

    assert result == {"s1": "a@example.com", "b@example.com": "b@example.com", "ghost": "ghost"}


async def test_resolve_many_with_nothing_to_resolve(db) -> None:
    assert await user_cache.resolve_many(db, []) == {}
