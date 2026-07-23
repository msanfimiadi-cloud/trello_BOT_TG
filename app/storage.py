from __future__ import annotations

import asyncio
import json
import sqlite3
from pathlib import Path

from .models import Session


class Storage:
    def __init__(self, path: Path):
        self.path = path
        self._locks: dict[str, asyncio.Lock] = {}

    async def initialize(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        await asyncio.to_thread(self._execute, "CREATE TABLE IF NOT EXISTS sessions (user_id INTEGER PRIMARY KEY, data TEXT NOT NULL, active INTEGER NOT NULL DEFAULT 1, updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)", ())

    def _execute(self, sql: str, params: tuple[object, ...]) -> list[tuple]:
        with sqlite3.connect(self.path) as connection:
            cursor = connection.execute(sql, params)
            return cursor.fetchall()

    async def save(self, session: Session) -> None:
        data = json.dumps(session.to_dict(), ensure_ascii=False)
        await asyncio.to_thread(self._execute, "INSERT INTO sessions(user_id,data,active) VALUES(?,?,1) ON CONFLICT(user_id) DO UPDATE SET data=excluded.data,active=1,updated_at=CURRENT_TIMESTAMP", (session.user_id, data))

    async def load(self, user_id: int) -> Session | None:
        rows = await asyncio.to_thread(self._execute, "SELECT data FROM sessions WHERE user_id=? AND active=1", (user_id,))
        if not rows:
            return None
        session = Session.from_dict(json.loads(rows[0][0]))
        # A process may die after persisting `creating`, while the remote result is
        # unknowable.  Never retry automatically: expose it as a failed task so a
        # human can decide whether to retry after checking Trello.
        changed = False
        for task in session.tasks:
            if task.status == "creating":
                task.status = "failed"
                task.last_error = "Создание было прервано; проверьте Trello перед повтором"
                changed = True
        if changed:
            await self.save(session)
        return session

    async def cancel(self, user_id: int) -> None:
        await asyncio.to_thread(self._execute, "UPDATE sessions SET active=0,updated_at=CURRENT_TIMESTAMP WHERE user_id=?", (user_id,))

    def creation_lock(self, task_uuid: str) -> asyncio.Lock:
        return self._locks.setdefault(task_uuid, asyncio.Lock())
