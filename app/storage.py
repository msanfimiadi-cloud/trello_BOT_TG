from __future__ import annotations

import asyncio
import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path

from .models import Session


@dataclass(frozen=True)
class User:
    telegram_user_id: int
    username: str | None
    full_name: str | None
    is_active: bool
    is_admin: bool
    created_at: str
    updated_at: str


class Storage:
    def __init__(self, path: Path):
        self.path = path
        self._locks: dict[str, asyncio.Lock] = {}

    async def initialize(self, admin_user_id: int | None = None, legacy_user_ids: frozenset[int] = frozenset()) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        await asyncio.to_thread(self._execute, "CREATE TABLE IF NOT EXISTS sessions (user_id INTEGER PRIMARY KEY, data TEXT NOT NULL, active INTEGER NOT NULL DEFAULT 1, updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)", ())
        await asyncio.to_thread(self._execute, "CREATE TABLE IF NOT EXISTS users (telegram_user_id INTEGER PRIMARY KEY, username TEXT, full_name TEXT, is_active INTEGER NOT NULL DEFAULT 0, is_admin INTEGER NOT NULL DEFAULT 0, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)", ())
        await asyncio.to_thread(self._execute, "CREATE TABLE IF NOT EXISTS admin_audit_log (id INTEGER PRIMARY KEY AUTOINCREMENT, admin_user_id INTEGER NOT NULL, target_user_id INTEGER NOT NULL, action TEXT NOT NULL, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)", ())
        await asyncio.to_thread(self._execute, "CREATE TABLE IF NOT EXISTS migrations (name TEXT PRIMARY KEY, applied_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)", ())
        if admin_user_id is not None:
            await asyncio.to_thread(self._execute, "INSERT INTO users(telegram_user_id,is_active,is_admin) VALUES(?,1,1) ON CONFLICT(telegram_user_id) DO UPDATE SET is_active=1,is_admin=1,updated_at=CURRENT_TIMESTAMP", (admin_user_id,))
            await asyncio.to_thread(self._migrate_allowlist, admin_user_id, legacy_user_ids)

    def _migrate_allowlist(self, admin_user_id: int, user_ids: frozenset[int]) -> None:
        with sqlite3.connect(self.path) as connection:
            if connection.execute("SELECT 1 FROM migrations WHERE name='legacy_allowlist_v1'").fetchone():
                return
            for user_id in user_ids | {admin_user_id}:
                connection.execute("INSERT INTO users(telegram_user_id,is_active,is_admin) VALUES(?,1,?) ON CONFLICT(telegram_user_id) DO UPDATE SET is_active=1", (user_id, int(user_id == admin_user_id)))
            connection.execute("INSERT INTO migrations(name) VALUES('legacy_allowlist_v1')")

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

    async def touch_user(self, user_id: int, username: str | None, full_name: str | None) -> None:
        await asyncio.to_thread(self._execute, "INSERT INTO users(telegram_user_id,username,full_name) VALUES(?,?,?) ON CONFLICT(telegram_user_id) DO UPDATE SET username=excluded.username,full_name=excluded.full_name,updated_at=CURRENT_TIMESTAMP", (user_id, username, full_name))

    async def has_access(self, user_id: int) -> bool:
        rows = await asyncio.to_thread(self._execute, "SELECT is_active FROM users WHERE telegram_user_id=?", (user_id,))
        return bool(rows and rows[0][0])

    async def is_admin(self, user_id: int) -> bool:
        rows = await asyncio.to_thread(self._execute, "SELECT is_admin,is_active FROM users WHERE telegram_user_id=?", (user_id,))
        return bool(rows and rows[0][0] and rows[0][1])

    async def set_access(self, admin_user_id: int, target_user_id: int, active: bool) -> bool:
        if await self.is_admin(target_user_id) and not active:
            return False
        await asyncio.to_thread(self._execute, "INSERT INTO users(telegram_user_id,is_active) VALUES(?,?) ON CONFLICT(telegram_user_id) DO UPDATE SET is_active=excluded.is_active,updated_at=CURRENT_TIMESTAMP", (target_user_id, int(active)))
        await asyncio.to_thread(self._execute, "INSERT INTO admin_audit_log(admin_user_id,target_user_id,action) VALUES(?,?,?)", (admin_user_id, target_user_id, "grant" if active else "revoke"))
        return True

    async def list_users(self, page: int, page_size: int = 8) -> tuple[list[User], int]:
        total = (await asyncio.to_thread(self._execute, "SELECT COUNT(*) FROM users", ()))[0][0]
        rows = await asyncio.to_thread(self._execute, "SELECT telegram_user_id,username,full_name,is_active,is_admin,created_at,updated_at FROM users ORDER BY is_admin DESC, updated_at DESC, telegram_user_id LIMIT ? OFFSET ?", (page_size, page * page_size))
        return [User(row[0], row[1], row[2], bool(row[3]), bool(row[4]), row[5], row[6]) for row in rows], total
