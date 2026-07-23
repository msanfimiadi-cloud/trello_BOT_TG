from pathlib import Path

import pytest

from app.models import Session, Task
from app.storage import Storage


@pytest.mark.asyncio
async def test_round_trip_and_cancel(tmp_path: Path):
    storage = Storage(tmp_path / "nested" / "bot.sqlite3")
    await storage.initialize()
    assert storage.path.exists()
    tasks = [Task("one", deadline="2026-12-31T18:00:00+03:00", no_deadline=False), Task("two", no_deadline=True)]
    tasks[0].status, tasks[0].member_id, tasks[0].assignee = "created", "member", "Иван"
    tasks[0].card_id, tasks[0].card_url = "card", "https://trello.com/c/card"
    tasks[1].status, tasks[1].manual_assignee, tasks[1].assignee = "skipped", True, "Пётр"
    session = Session(1, 2, "meeting", "source", tasks, current_index=1, phase="confirm")
    await storage.save(session)
    restored = await storage.load(1)
    assert restored == session
    await storage.cancel(1)
    assert await storage.load(1) is None


@pytest.mark.asyncio
async def test_interrupted_creation_is_not_retried_or_blocked(tmp_path: Path):
    storage = Storage(tmp_path / "bot.sqlite3")
    await storage.initialize()
    session = Session(1, 2, "meeting", "source", [Task("one", status="creating")], phase="confirm")
    await storage.save(session)
    # A new Storage instance simulates process restart.
    recovered = await Storage(storage.path).load(1)
    assert recovered.tasks[0].status == "failed"
    assert "проверьте Trello" in recovered.tasks[0].last_error
    assert (await Storage(storage.path).load(1)).tasks[0].status == "failed"
