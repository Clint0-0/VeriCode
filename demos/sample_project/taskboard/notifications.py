"""Notification formatting and throttling (unrelated to the demo tasks; adds realistic repo context)."""
from __future__ import annotations

import time
from collections import defaultdict, deque
from dataclasses import dataclass, field


@dataclass
class Notification:
    channel: str
    recipient: str
    subject: str
    body: str
    created_at: float = field(default_factory=time.time)


class Throttle:
    """Allow at most `limit` notifications per recipient per `window` seconds."""

    def __init__(self, limit: int = 5, window: float = 60.0) -> None:
        self.limit = limit
        self.window = window
        self._sent: dict[str, deque[float]] = defaultdict(deque)

    def allow(self, recipient: str, now: float | None = None) -> bool:
        now = time.time() if now is None else now
        q = self._sent[recipient]
        while q and now - q[0] > self.window:
            q.popleft()
        if len(q) >= self.limit:
            return False
        q.append(now)
        return True


def format_digest(recipient: str, items: list[str]) -> Notification:
    body = "\n".join(f"* {i}" for i in items) or "Nothing new today."
    return Notification("email", recipient, f"Your taskboard digest ({len(items)})", body)


def format_mention(recipient: str, author: str, task_title: str) -> Notification:
    return Notification("chat", recipient, "You were mentioned", f"{author} mentioned you on '{task_title}'")
