from __future__ import annotations

import re
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

DATE_FRAGMENT = re.compile(r"(?<!\d)(\d{1,2}\.\d{1,2}(?:\.\d{2}|\.\d{4})?)(?!\d)")
DATE_FULL = re.compile(r"^(\d{1,2})\.(\d{1,2})(?:\.(\d{2}|\d{4}))?$")


def parse_date(value: str, timezone: ZoneInfo, now: datetime | None = None) -> datetime | None:
    normalized = value.strip().lower()
    current = (now or datetime.now(timezone)).astimezone(timezone)
    offsets = {"сегодня": 0, "завтра": 1, "послезавтра": 2}
    if normalized in {"нет", "без дедлайна"}:
        return None
    if normalized in offsets:
        target = current.date() + timedelta(days=offsets[normalized])
    else:
        match = DATE_FULL.fullmatch(normalized)
        if not match:
            raise ValueError("Введите дату целиком в формате ДД.ММ, ДД.ММ.ГГ или ДД.ММ.ГГГГ")
        day, month, year_text = match.groups()
        year = current.year if year_text is None else int(year_text)
        if year_text and len(year_text) == 2:
            year += 2000
        try:
            target = date(year, int(month), int(day))
        except ValueError as exc:
            raise ValueError("Такой календарной даты не существует") from exc
        if year_text is None and target < current.date():
            target = target.replace(year=year + 1)
    return datetime.combine(target, time(18, 0), timezone)


def extract_date(text: str, timezone: ZoneInfo, now: datetime | None = None) -> datetime | None:
    relative = re.search(r"(?i)(?<!\w)(послезавтра|завтра|сегодня)(?!\w)", text)
    if relative:
        return parse_date(relative.group(1), timezone, now)
    for match in DATE_FRAGMENT.finditer(text):
        try:
            return parse_date(match.group(1), timezone, now)
        except ValueError:
            continue
    return None


def display_date(value: str | datetime | None) -> str:
    if value is None:
        return "без дедлайна"
    dt = datetime.fromisoformat(value) if isinstance(value, str) else value
    return dt.strftime("%d.%m.%Y")
