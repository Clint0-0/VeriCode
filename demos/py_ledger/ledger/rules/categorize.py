from __future__ import annotations

import re
from dataclasses import dataclass

from ..io.csv_import import BankLine
from ..journal import JournalEntry, simple_entry


@dataclass(frozen=True)
class Rule:
    pattern: str  # case-insensitive regular expression matched against the payee
    account: str  # income account for money in, expense account for money out
    tag: str = ""


class Categorizer:
    """First matching rule wins; unmatched lines go to the suspense account."""

    def __init__(self, rules: list[Rule], bank_account: str, suspense_account: str) -> None:
        self.rules = [(re.compile(r.pattern, re.I), r) for r in rules]
        self.bank_account = bank_account
        self.suspense_account = suspense_account

    def match(self, line: BankLine) -> Rule | None:
        for rx, rule in self.rules:
            if rx.search(line.payee):
                return rule
        return None

    def to_entry(self, line: BankLine) -> JournalEntry:
        rule = self.match(line)
        other = rule.account if rule else self.suspense_account
        desc = f"{line.payee} {line.reference}".strip()[:140]
        if line.amount >= 0:
            entry = simple_entry(line.date, desc, self.bank_account, other, line.amount)
        else:
            entry = simple_entry(line.date, desc, other, self.bank_account, -line.amount)
        if rule and rule.tag:
            entry = entry.model_copy(update={"tags": [rule.tag]})
        return entry

    def categorize(self, lines: list[BankLine]) -> tuple[list[JournalEntry], list[BankLine]]:
        entries, unmatched = [], []
        for line in lines:
            if self.match(line) is None:
                unmatched.append(line)
            entries.append(self.to_entry(line))
        return entries, unmatched
