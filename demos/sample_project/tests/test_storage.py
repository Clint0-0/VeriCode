from datetime import datetime, timedelta

from taskboard import Priority, TaskStore


def test_add_and_get():
    s = TaskStore()
    t = s.add("Write docs", Priority.HIGH)
    assert s.get(t.id).title == "Write docs"


def test_overdue():
    s = TaskStore()
    now = datetime(2026, 1, 10)
    s.add("late", due=now - timedelta(days=1))
    s.add("future", due=now + timedelta(days=1))
    assert [t.title for t in s.overdue(now)] == ["late"]
