from __future__ import annotations

from datetime import datetime

from .models import Priority, Task


class TaskStore:
    """In-memory task repository."""

    def __init__(self) -> None:
        self._tasks: dict[int, Task] = {}
        self._next_id = 1

    def add(self, title: str, priority: Priority = Priority.MEDIUM, due: datetime | None = None,
            tags: list[str] | None = None) -> Task:
        task = Task(id=self._next_id, title=title, priority=priority, due=due, tags=tags or [])
        self._tasks[task.id] = task
        self._next_id += 1
        return task

    def get(self, task_id: int) -> Task:
        if task_id not in self._tasks:
            raise KeyError(f"task {task_id} not found")
        return self._tasks[task_id]

    def complete(self, task_id: int) -> Task:
        task = self.get(task_id)
        task.done = True
        return task

    def all(self) -> list[Task]:
        return list(self._tasks.values())

    def overdue(self, now: datetime) -> list[Task]:
        return [t for t in self._tasks.values() if t.is_overdue(now)]
