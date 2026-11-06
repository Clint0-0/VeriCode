from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field


class Priority(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class Task(BaseModel):
    id: int
    title: str = Field(min_length=1, max_length=200)
    priority: Priority = Priority.MEDIUM
    done: bool = False
    due: datetime | None = None
    tags: list[str] = []

    def is_overdue(self, now: datetime) -> bool:
        return bool(self.due and not self.done and self.due < now)
