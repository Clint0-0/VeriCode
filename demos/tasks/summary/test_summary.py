"""Acceptance tests for demo task 2 (priority summary)."""
from taskboard import Priority, TaskStore


def test_priority_summary_counts_open_tasks():
    s = TaskStore()
    s.add("a", Priority.HIGH)
    s.add("b", Priority.HIGH)
    done = s.add("c", Priority.LOW)
    s.complete(done.id)
    assert s.priority_summary() == {"low": 0, "medium": 0, "high": 2}
