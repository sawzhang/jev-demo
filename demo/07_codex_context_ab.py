"""Read-only Codex A/B: all candidate files vs Jev-selected files.

Uses one fixed task from 06_codex_file_selection.py. Run from the repository root.
"""
from __future__ import annotations

import json
from pathlib import Path
import subprocess

from importlib.util import module_from_spec, spec_from_file_location

ROOT = Path(__file__).resolve().parents[1]
spec = spec_from_file_location("file_selection", Path(__file__).with_name("06_codex_file_selection.py"))
module = module_from_spec(spec)
spec.loader.exec_module(module)

TASK = "Fix the date-window judgment in the Jev benchmark. Identify the file and existing test case to change. Do not edit files."
# Top 3 from the full-file mode of 06_codex_file_selection.py, 2026-09-22.
SELECTED = ["demo/05_benchmark.py", "docs/05-limitations.md", "demo/01_triage.py"]


def run(label: str, paths: list[str]) -> None:
    context = "\n\n".join(f"### {path}\n{(ROOT / path).read_text()}" for path in paths)
    prompt = ("Use only the supplied repository files. Answer in two sentences: which exact "
              "file and test case should change, and what correction is needed?\n\n"
              f"Task: {TASK}\n\n{context}")
    cmd = ["codex", "exec", "--json", "--ephemeral", "--skip-git-repo-check",
           "--sandbox", "read-only", "--cd", "/private/tmp", "-"]
    result = subprocess.run(cmd, input=prompt, text=True, capture_output=True, check=False)
    events = []
    for line in result.stdout.splitlines():
        try:
            events.append(json.loads(line))
        except json.JSONDecodeError:
            pass
    completed = [e for e in events if e.get("type") == "turn.completed"]
    messages = [e.get("item", {}).get("text", "") for e in events
                if e.get("type") == "item.completed" and e.get("item", {}).get("type") == "agent_message"]
    print(f"\n{label}: {len(paths)} files, {len(prompt)} prompt chars, exit={result.returncode}")
    print("Usage:", completed[-1].get("usage") if completed else "unavailable")
    print("Answer:", messages[-1] if messages else "unavailable")
    if result.returncode:
        print("Error:", result.stderr[-1000:])


if __name__ == "__main__":
    run("All files", module.FILES)
    run("Jev top 3", SELECTED)
