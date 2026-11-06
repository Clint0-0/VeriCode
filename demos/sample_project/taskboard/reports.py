"""Plain-text and CSV reporting (unrelated to the demo tasks; adds realistic repo context)."""
from __future__ import annotations

import csv
import io
from collections import Counter
from datetime import datetime

from .models import Task


def completion_rate(tasks: list[Task]) -> float:
    if not tasks:
        return 0.0
    return round(sum(t.done for t in tasks) / len(tasks), 3)


def tag_histogram(tasks: list[Task]) -> dict[str, int]:
    c: Counter[str] = Counter()
    for t in tasks:
        c.update(t.tags)
    return dict(c.most_common())


def to_csv(tasks: list[Task]) -> str:
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["id", "title", "priority", "done", "due", "tags"])
    for t in tasks:
        w.writerow([t.id, t.title, t.priority.value, t.done, t.due.isoformat() if t.due else "", ";".join(t.tags)])
    return buf.getvalue()


def text_report(tasks: list[Task], now: datetime) -> str:
    lines = [f"Tasks: {len(tasks)}", f"Completion: {completion_rate(tasks):.0%}"]
    overdue = [t for t in tasks if t.is_overdue(now)]
    if overdue:
        lines.append("Overdue:")
        lines += [f"  - #{t.id} {t.title} (due {t.due:%Y-%m-%d})" for t in overdue]
    hist = tag_histogram(tasks)
    if hist:
        lines.append("Tags: " + ", ".join(f"{k}={v}" for k, v in hist.items()))
    return "\n".join(lines)
