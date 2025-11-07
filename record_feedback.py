#!/usr/bin/env python3
"""
Record verified ethnicity labels so future runs can reuse them.

Usage:
  python3 record_feedback.py --name "Rahul Sharma" --ethnicity "Indian"
  python3 record_feedback.py --from-csv corrections.csv
"""
from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

from feedback_store import FeedbackEntry, FeedbackStore

DEFAULT_STORE = Path(__file__).resolve().parent / "feedback.csv"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Append feedback entries.")
    parser.add_argument(
        "--store",
        default=str(DEFAULT_STORE),
        help="Path to the feedback CSV (defaults to ./feedback.csv).",
    )

    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--name", help="Single name to record.")
    source.add_argument("--from-csv", dest="from_csv", help="CSV file with name,ethnicity[,notes].")

    parser.add_argument("--ethnicity", help="Ethnicity label for --name mode.")
    parser.add_argument("--notes", default="", help="Optional notes for --name mode.")
    return parser.parse_args()


def import_csv(path: Path) -> list[FeedbackEntry]:
    entries: list[FeedbackEntry] = []
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        if "name" not in reader.fieldnames or "ethnicity" not in reader.fieldnames:
            raise ValueError("CSV must include 'name' and 'ethnicity' columns.")
        for row in reader:
            name = (row.get("name") or "").strip()
            ethnicity = (row.get("ethnicity") or "").strip()
            notes = (row.get("notes") or "").strip()
            if not name or not ethnicity:
                continue
            entries.append(FeedbackEntry(name=name, ethnicity=ethnicity, notes=notes))
    return entries


def main() -> int:
    args = parse_args()
    store = FeedbackStore(Path(args.store).expanduser())

    if args.name:
        if not args.ethnicity:
            print("--ethnicity is required when using --name.", file=sys.stderr)
            return 1
        store.append(args.name, args.ethnicity, args.notes)
        print(f"Recorded feedback for {args.name} -> {args.ethnicity}")
        return 0

    try:
        entries = import_csv(Path(args.from_csv).expanduser())
    except Exception as exc:  # noqa: BLE001
        print(f"Failed to import CSV: {exc}", file=sys.stderr)
        return 1

    if not entries:
        print("No valid feedback rows found.", file=sys.stderr)
        return 1

    store.extend(entries)
    print(f"Imported {len(entries)} feedback rows into {store.path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
