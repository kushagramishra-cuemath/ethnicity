#!/usr/bin/env python3
"""Lightweight helper to load and update human feedback labels."""
from __future__ import annotations

import csv
from dataclasses import dataclass
from difflib import SequenceMatcher
from pathlib import Path
from typing import Iterable, List, Optional


@dataclass
class FeedbackEntry:
    name: str
    ethnicity: str
    notes: str = ""


class FeedbackStore:
    """Persists verified name→ethnicity mappings that we can reuse later."""

    def __init__(self, path: Path):
        self.path = Path(path)
        self.entries: List[FeedbackEntry] = []
        self._by_name: dict[str, FeedbackEntry] = {}
        self._load()

    @staticmethod
    def _normalize(name: str) -> str:
        return name.strip().lower()

    def _load(self) -> None:
        if not self.path.exists():
            return

        with self.path.open(newline="", encoding="utf-8") as handle:
            reader = csv.DictReader(handle)
            for row in reader:
                name = (row.get("name") or "").strip()
                ethnicity = (row.get("ethnicity") or "").strip()
                notes = (row.get("notes") or "").strip()
                if not name or not ethnicity:
                    continue
                entry = FeedbackEntry(name=name, ethnicity=ethnicity, notes=notes)
                self.entries.append(entry)
                self._by_name[self._normalize(name)] = entry

    def lookup(self, name: str) -> Optional[FeedbackEntry]:
        return self._by_name.get(self._normalize(name))

    def sample(self, count: int) -> List[FeedbackEntry]:
        if count <= 0:
            return []
        return self.entries[:count]

    def similar_examples(self, name: str, count: int) -> List[FeedbackEntry]:
        if count <= 0 or not name or not self.entries:
            return []

        scored = []
        for entry in self.entries:
            ratio = SequenceMatcher(
                None, self._normalize(name), self._normalize(entry.name)
            ).ratio()
            scored.append((ratio, entry))

        scored.sort(key=lambda pair: pair[0], reverse=True)
        results: List[FeedbackEntry] = []
        for ratio, entry in scored:
            if ratio <= 0:
                continue
            results.append(entry)
            if len(results) >= count:
                break
        return results

    def append(self, name: str, ethnicity: str, notes: str = "") -> None:
        entry = FeedbackEntry(name=name.strip(), ethnicity=ethnicity.strip(), notes=notes.strip())
        if not entry.name or not entry.ethnicity:
            raise ValueError("Both name and ethnicity must be provided.")

        self._add_entry(entry)
        self._persist()

    def extend(self, entries: Iterable[FeedbackEntry]) -> None:
        added = False
        for entry in entries:
            if not entry.name.strip() or not entry.ethnicity.strip():
                continue
            clean = FeedbackEntry(
                name=entry.name.strip(),
                ethnicity=entry.ethnicity.strip(),
                notes=entry.notes.strip(),
            )
            self._add_entry(clean)
            added = True
        if added:
            self._persist()

    def _add_entry(self, entry: FeedbackEntry) -> None:
        self.entries.append(entry)
        self._by_name[self._normalize(entry.name)] = entry

    def _persist(self) -> None:
        with self.path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=["name", "ethnicity", "notes"])
            writer.writeheader()
            for entry in self.entries:
                writer.writerow(
                    {
                        "name": entry.name,
                        "ethnicity": entry.ethnicity,
                        "notes": entry.notes,
                    }
                )
