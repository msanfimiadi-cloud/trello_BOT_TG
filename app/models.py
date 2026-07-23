from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any
from uuid import uuid4


@dataclass
class Task:
    text: str
    uuid: str = field(default_factory=lambda: str(uuid4()))
    deadline: str | None = None
    no_deadline: bool = False
    assignee: str | None = None
    member_id: str | None = None
    manual_assignee: bool = False
    status: str = "pending"
    card_id: str | None = None
    card_url: str | None = None
    created_at: str | None = None
    last_error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "Task":
        return cls(**value)


@dataclass
class Session:
    user_id: int
    chat_id: int
    meeting_title: str
    source_text: str
    tasks: list[Task]
    current_index: int = 0
    phase: str = "preview"

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        return data

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "Session":
        value = dict(value)
        value["tasks"] = [Task.from_dict(item) for item in value["tasks"]]
        return cls(**value)
