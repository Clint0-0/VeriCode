from __future__ import annotations

import json

from pydantic import TypeAdapter

from ..journal import JournalEntry

_ENTRIES = TypeAdapter(list[JournalEntry])


def export_entries(entries: list[JournalEntry]) -> str:
    """JSON array; dates as ISO strings, Decimal amounts as strings (exact round trip)."""
    return json.dumps(_ENTRIES.dump_python(entries, mode="json"))


def import_entries(text: str) -> list[JournalEntry]:
    entries = _ENTRIES.validate_json(text)
    for e in entries:
        e.check_balanced()
    return entries
