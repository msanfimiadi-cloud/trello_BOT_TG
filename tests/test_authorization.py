import sqlite3

import pytest

from app.storage import Storage


@pytest.mark.asyncio
async def test_admin_and_access_lifecycle_is_persistent(tmp_path):
    storage = Storage(tmp_path / "bot.sqlite3")
    await storage.initialize(100)
    assert await storage.is_admin(100)
    assert await storage.has_access(100)
    assert not await storage.has_access(200)

    await storage.touch_user(200, "worker", "Worker Name")
    users, total = await storage.list_users(0)
    assert total == 2
    assert next(user for user in users if user.telegram_user_id == 200).username == "worker"
    assert await storage.set_access(100, 200, True)
    assert await storage.has_access(200)
    assert await storage.set_access(100, 200, False)
    assert not await storage.has_access(200)
    assert not await storage.set_access(100, 100, False)

    with sqlite3.connect(storage.path) as connection:
        assert connection.execute("SELECT action FROM admin_audit_log ORDER BY id").fetchall() == [("grant",), ("revoke",)]


@pytest.mark.asyncio
async def test_legacy_allowlist_migrates_exactly_once(tmp_path):
    storage = Storage(tmp_path / "bot.sqlite3")
    await storage.initialize(100, frozenset({200}))
    assert await storage.has_access(200)
    await storage.set_access(100, 200, False)

    await storage.initialize(100, frozenset({200, 300}))
    assert not await storage.has_access(200)
    assert not await storage.has_access(300)


@pytest.mark.asyncio
async def test_user_list_is_paginated(tmp_path):
    storage = Storage(tmp_path / "bot.sqlite3")
    await storage.initialize(100)
    for user_id in range(200, 218):
        await storage.touch_user(user_id, None, None)
    first, total = await storage.list_users(0, page_size=8)
    second, _ = await storage.list_users(1, page_size=8)
    assert total == 19
    assert len(first) == len(second) == 8
    assert {user.telegram_user_id for user in first}.isdisjoint(user.telegram_user_id for user in second)
