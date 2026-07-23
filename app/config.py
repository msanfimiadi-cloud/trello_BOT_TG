from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


class ConfigurationError(RuntimeError):
    pass


@dataclass(frozen=True)
class Settings:
    telegram_token: str
    trello_key: str
    trello_token: str
    trello_list_id: str
    admin_telegram_user_id: int
    timezone: ZoneInfo
    database_path: Path = Path("data/bot.sqlite3")
    legacy_team: dict[str, str] = field(default_factory=dict, repr=False)
    legacy_allowed_user_ids: frozenset[int] = field(default_factory=frozenset, repr=False)

    @classmethod
    def from_env(cls) -> "Settings":
        names = ("TELEGRAM_BOT_TOKEN", "TRELLO_API_KEY", "TRELLO_API_TOKEN", "TRELLO_LIST_ID", "ADMIN_TELEGRAM_USER_ID")
        missing = [name for name in names if not os.getenv(name, "").strip()]
        if missing:
            raise ConfigurationError("Не заданы обязательные переменные окружения: " + ", ".join(missing))
        try:
            admin_id = int(os.environ["ADMIN_TELEGRAM_USER_ID"].strip())
        except ValueError as exc:
            raise ConfigurationError("ADMIN_TELEGRAM_USER_ID должен быть целым числом") from exc
        if admin_id <= 0:
            raise ConfigurationError("ADMIN_TELEGRAM_USER_ID должен быть положительным")
        try:
            legacy_allowed = frozenset(int(item.strip()) for item in os.getenv("ALLOWED_TELEGRAM_USER_IDS", "").split(",") if item.strip())
        except ValueError as exc:
            raise ConfigurationError("Устаревший ALLOWED_TELEGRAM_USER_IDS должен содержать Telegram ID через запятую") from exc
        try:
            timezone = ZoneInfo(os.getenv("BOT_TIMEZONE", "Europe/Moscow"))
        except ZoneInfoNotFoundError as exc:
            raise ConfigurationError("Неизвестная таймзона BOT_TIMEZONE") from exc
        try:
            team = json.loads(os.getenv("TEAM_JSON", "{}").strip() or "{}")
            if not isinstance(team, dict) or not all(isinstance(k, str) and isinstance(v, str) for k, v in team.items()):
                raise ValueError
        except (json.JSONDecodeError, ValueError) as exc:
            raise ConfigurationError("TEAM_JSON должен быть JSON-объектом вида имя: Trello member ID") from exc
        return cls(os.environ["TELEGRAM_BOT_TOKEN"], os.environ["TRELLO_API_KEY"], os.environ["TRELLO_API_TOKEN"], os.environ["TRELLO_LIST_ID"], admin_id, timezone, Path(os.getenv("DATABASE_PATH", "data/bot.sqlite3")), team, legacy_allowed)
