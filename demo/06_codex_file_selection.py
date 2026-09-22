"""Measure whether Jev can select useful repo files before a Codex task.

This tests retrieval only. It does not modify Codex's internal context assembly.
Run from the repository root: .venv/bin/python demo/06_codex_file_selection.py
"""
from __future__ import annotations

import os
import argparse
from pathlib import Path
import sys
import time

sys.path.insert(0, str(Path(__file__).parent))
from jev_lite import load_env  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
load_env(str(ROOT / ".env"))

from typesafe_sdk import Score, TypeSafeClient  # noqa: E402

FILES = [
    "demo/01_triage.py",
    "demo/02_guardrails.py",
    "demo/03_semantic_rerank.py",
    "demo/04_function_calling.py",
    "demo/05_benchmark.py",
    "docs/02-primitives.md",
    "docs/03-confidence.md",
    "docs/05-limitations.md",
]

CASES = [
    ("Fix the date-window judgment in the Jev benchmark", {"demo/05_benchmark.py", "docs/05-limitations.md"}),
    ("Handle a smart-home request that asks for two actions", {"demo/04_function_calling.py"}),
    ("Add a confidence gate to support-ticket triage", {"demo/01_triage.py", "docs/03-confidence.md"}),
]

RUBRIC = [
    "Unrelated to this coding task",
    "Same broad topic, but unlikely to help implement the task",
    "Useful background or a related implementation",
    "Directly needed to implement or verify the task",
]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--preview-chars", type=int, default=0,
                        help="Send only this many characters from each file to Jev (0 = full file)")
    args = parser.parse_args()
    client = TypeSafeClient()
    contents = {name: (ROOT / name).read_text() for name in FILES}
    previews = {name: value[:args.preview_chars] if args.preview_chars else value
                for name, value in contents.items()}
    total_bytes = sum(len(value.encode()) for value in contents.values())
    total_tokens = 0
    for task, expected in CASES:
        questions = {
            f"file_{i}": Score(
                instructions={"task": task, "path": name, "content": previews[name]},
                criteria=RUBRIC,
            )
            for i, name in enumerate(FILES)
        }
        start = time.monotonic()
        result = client.system_one(state={"task": task}, questions=questions)
        elapsed = time.monotonic() - start
        total_tokens += result.usage.input_tokens
        ranked = sorted(
            ((name, result.answers[f"file_{i}"].score) for i, name in enumerate(FILES)),
            key=lambda item: item[1], reverse=True,
        )
        selected = {name for name, _ in ranked[:3]}
        sent_bytes = sum(len(contents[name].encode()) for name in selected)
        recall = len(selected & expected) / len(expected)
        print(f"\nTask: {task}")
        print(f"Expected: {', '.join(sorted(expected))}")
        print(f"Top 3: {', '.join(f'{name} ({score:.2f})' for name, score in ranked[:3])}")
        print(f"Recall@3: {recall:.0%}; file bytes passed: {sent_bytes}/{total_bytes} "
              f"({sent_bytes / total_bytes:.0%}); Jev input tokens: {result.usage.input_tokens}; "
              f"latency: {elapsed:.2f}s")
    print(f"\nTotal Jev input tokens: {total_tokens}")
    print("File bytes are only a context-volume proxy, not measured Codex tokens.")


if __name__ == "__main__":
    main()
