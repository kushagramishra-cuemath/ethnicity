#!/usr/bin/env python3
"""
Annotate a CSV of signups with an ethnicity label inferred from each name.

Usage:
  python3 mark_ethnicity.py input.csv [output.csv] [--limit 100]

Environment:
  OPENAI_API_KEY   (required) - set via environment or .env file alongside this script.
  OPENAI_MODEL     (optional) - defaults to gpt-4o-mini.
  OPENAI_CA_BUNDLE (optional) - path to CA bundle for TLS verification.
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import ssl
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Iterable, List, Sequence

from feedback_store import FeedbackEntry, FeedbackStore


REPO_ROOT = Path(__file__).resolve().parent
DEFAULT_CA_BUNDLE = "/etc/ssl/cert.pem"
DEFAULT_PROMPT = (
    "You classify the most likely ethnicity for a given personal name of a signup. "
    "Return a single concise label (e.g. 'Indian', 'East Asian', 'Middle Eastern', "
    "'African', 'European', 'Latino', 'Mixed', or 'Unknown'). "
    "Use 'Unknown' if the ethnicity cannot be determined confidently from the name alone."
)
API_URL = "https://api.openai.com/v1/chat/completions"


def load_env() -> None:
    env_path = REPO_ROOT / ".env"
    if not env_path.exists():
        return
    for line in env_path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        os.environ.setdefault(key, value)


def build_ssl_context() -> ssl.SSLContext:
    bundle_path = os.environ.get("OPENAI_CA_BUNDLE", DEFAULT_CA_BUNDLE)
    if bundle_path and Path(bundle_path).exists():
        return ssl.create_default_context(cafile=bundle_path)
    return ssl.create_default_context()


def build_prompt(base_prompt: str, examples: Sequence[FeedbackEntry]) -> str:
    if not examples:
        return base_prompt

    lines = [base_prompt, "", "Previously approved mappings:"]
    for entry in examples:
        note_segment = f" ({entry.notes})" if entry.notes else ""
        lines.append(f"- {entry.name} -> {entry.ethnicity}{note_segment}")
    return "\n".join(lines)


def call_openai(name: str, prompt: str, model: str, context: ssl.SSLContext) -> str:
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": prompt},
            {"role": "user", "content": f"Name: {name}"},
        ],
        "temperature": 0,
    }
    request = urllib.request.Request(
        API_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {os.environ['OPENAI_API_KEY']}",
            "Content-Type": "application/json",
        },
        method="POST",
    )

    max_attempts = 3
    for attempt in range(1, max_attempts + 1):
        try:
            with urllib.request.urlopen(request, context=context) as response:
                data = json.load(response)
            return data["choices"][0]["message"]["content"].strip()
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", "ignore")
            if exc.code in {429, 500, 502, 503, 504} and attempt < max_attempts:
                time.sleep(2 * attempt)
                continue
            raise RuntimeError(f"HTTP error {exc.code}: {body}") from exc
        except urllib.error.URLError as exc:
            if attempt < max_attempts:
                time.sleep(2 * attempt)
                continue
            raise RuntimeError(f"Network error: {exc.reason}") from exc
        except (KeyError, IndexError) as exc:
            raise RuntimeError(f"Unexpected response: {json.dumps(data, indent=2)}") from exc


def insert_ethnicity(row: List[str], ethnicity: str) -> List[str]:
    new_row = list(row)
    new_row.insert(1, ethnicity)
    return new_row


def read_csv(path: Path) -> List[List[str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return [row for row in csv.reader(handle)]


def write_csv(path: Path, rows: Iterable[List[str]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        for row in rows:
            writer.writerow(row)


def process_rows(
    rows: List[List[str]],
    prompt: str,
    model: str,
    limit: int | None,
    has_header: bool,
    store: FeedbackStore,
    fewshot_count: int,
    force_api: bool,
) -> List[List[str]]:
    context = build_ssl_context()
    start_index = 1 if (has_header and rows) else 0
    output_rows: List[List[str]] = []

    if has_header and rows:
        header = list(rows[0])
        header.insert(1, "Ethnicity")
        output_rows.append(header)

    processed = 0
    for idx, row in enumerate(rows[start_index:], start=start_index):
        if limit is not None and processed >= limit:
            # Preserve row but leave ethnicity blank for unprocessed entries.
            output_rows.append(insert_ethnicity(row, ""))
            continue

        name = row[0].strip() if row else ""
        if not name:
            label = "Unknown"
        else:
            cached = None if force_api else store.lookup(name)
            if cached:
                label = cached.ethnicity
            else:
                examples = store.similar_examples(name, fewshot_count) or store.sample(fewshot_count)
                label = call_openai(name, build_prompt(prompt, examples), model, context)

        output_rows.append(insert_ethnicity(row, label))
        processed += 1

    if not has_header:
        return output_rows

    return output_rows


def derive_output_path(input_path: Path, explicit: str | None) -> Path:
    if explicit:
        return Path(explicit).expanduser().resolve()
    return input_path.with_name(f"{input_path.stem}_with_ethnicity.csv")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Annotate signups with ethnicity.")
    parser.add_argument("input_csv", help="Path to the CSV containing signups.")
    parser.add_argument(
        "output_csv",
        nargs="?",
        help="Where to write the annotated CSV (defaults to <input>_with_ethnicity.csv).",
    )
    parser.add_argument(
        "--prompt-file",
        type=str,
        help="Custom prompt instructions for the model.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        help="Only process the first N signups (useful for sampling).",
    )
    parser.add_argument(
        "--no-header",
        action="store_true",
        help="Set if the CSV does not contain a header row.",
    )
    parser.add_argument(
        "--model",
        type=str,
        help="Override the OpenAI model (defaults to environment or gpt-4o-mini).",
    )
    parser.add_argument(
        "--feedback-store",
        type=str,
        default=str(REPO_ROOT / "feedback.csv"),
        help="CSV file containing verified name→ethnicity mappings.",
    )
    parser.add_argument(
        "--fewshot-count",
        type=int,
        default=5,
        help="How many feedback examples to include as guidance in the prompt.",
    )
    parser.add_argument(
        "--force-api",
        action="store_true",
        help="Always call OpenAI even if the feedback store contains a label for the name.",
    )
    return parser.parse_args()


def main() -> int:
    load_env()
    args = parse_args()

    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        print("OPENAI_API_KEY is not set. Add it to .env or the environment.", file=sys.stderr)
        return 1

    prompt = DEFAULT_PROMPT
    if args.prompt_file:
        prompt_path = Path(args.prompt_file)
        if not prompt_path.exists():
            print(f"Prompt file not found: {prompt_path}", file=sys.stderr)
            return 1
        prompt = prompt_path.read_text(encoding="utf-8").strip()

    model = args.model or os.environ.get("OPENAI_MODEL", "gpt-4o-mini")

    input_path = Path(args.input_csv).expanduser().resolve()
    if not input_path.exists():
        print(f"Input CSV not found: {input_path}", file=sys.stderr)
        return 1

    try:
        rows = read_csv(input_path)
    except Exception as exc:  # noqa: BLE001
        print(f"Failed to read CSV: {exc}", file=sys.stderr)
        return 1

    output_path = derive_output_path(input_path, args.output_csv)
    feedback_store = FeedbackStore(Path(args.feedback_store).expanduser())

    try:
        annotated = process_rows(
            rows,
            prompt=prompt,
            model=model,
            limit=args.limit,
            has_header=not args.no_header,
            store=feedback_store,
            fewshot_count=max(0, args.fewshot_count),
            force_api=args.force_api,
        )
    except Exception as exc:  # noqa: BLE001
        print(f"Failed to classify names: {exc}", file=sys.stderr)
        return 1

    write_csv(output_path, annotated)
    print(f"Wrote annotated CSV to {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
