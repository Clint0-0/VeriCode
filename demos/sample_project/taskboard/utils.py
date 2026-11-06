"""Misc helpers (unrelated to the demo tasks; adds realistic repo context)."""
from __future__ import annotations

import re
import unicodedata
from datetime import datetime, timedelta, timezone


def slugify(text: str) -> str:
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def parse_duration(spec: str) -> timedelta:
    m = re.fullmatch(r"(\d+)([smhd])", spec.strip())
    if not m:
        raise ValueError(f"bad duration {spec!r}")
    n, unit = int(m.group(1)), m.group(2)
    return {"s": timedelta(seconds=n), "m": timedelta(minutes=n), "h": timedelta(hours=n), "d": timedelta(days=n)}[unit]


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def chunked(seq: list, size: int) -> list[list]:
    if size < 1:
        raise ValueError("size must be >= 1")
    return [seq[i:i + size] for i in range(0, len(seq), size)]


def truncate(text: str, limit: int = 80) -> str:
    return text if len(text) <= limit else text[: limit - 1] + "…"
