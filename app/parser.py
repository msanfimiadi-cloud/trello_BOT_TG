from __future__ import annotations

import re
from datetime import datetime
from zoneinfo import ZoneInfo

from .dates import extract_date
from .models import Task

ITEM = re.compile(r"(?m)^\s*\d+\s*(?:\.|\)|-)\s*(?=\S)")
LEADING_DATE = re.compile(r"^\s*(?:\d{1,2}\.\d{1,2}(?:\.\d{2,4})?|сегодня|завтра|послезавтра)\s*(?:[-—–:,.]\s*)?", re.I)


def parse_meeting(text: str, timezone: ZoneInfo, now: datetime | None = None) -> tuple[str, list[Task]]:
    lines = text.splitlines()
    title_index = next((i for i, line in enumerate(lines) if line.strip()), None)
    if title_index is None:
        return "", []
    title = lines[title_index].strip()
    body = "\n".join(lines[title_index + 1 :])
    matches = list(ITEM.finditer(body))
    tasks: list[Task] = []
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(body)
        value = body[match.end():end].strip()
        if value:
            deadline = extract_date(value, timezone, now)
            tasks.append(Task(text=value, deadline=deadline.isoformat() if deadline else None))
    return title, tasks


def card_title(task_text: str, maximum: int = 150) -> str:
    first = next((line.strip() for line in task_text.splitlines() if line.strip()), "Задача")
    first = LEADING_DATE.sub("", first).strip() or "Задача"
    if len(first) <= maximum:
        return first
    shortened = first[: maximum + 1].rsplit(maxsplit=1)[0].rstrip(" ,.;:-—")
    return shortened or first[:maximum]


def card_description(
    meeting: str,
    text: str,
    manual_name: str | None = None,
    task_reference: str | None = None,
) -> str:
    result = f"Из встречи: {meeting}\n\nИсходный текст:\n{text}"
    if manual_name:
        result += f"\n\nОтветственный, указанный вручную:\n{manual_name}"
    if task_reference:
        # The stable marker lets us reconcile an ambiguous network timeout with
        # Trello before retrying, instead of creating the same card twice.
        result += f"\n\nСистемный ID задачи: {task_reference}"
    return result
