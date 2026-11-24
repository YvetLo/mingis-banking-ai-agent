"""
Shared golden-set loader for tests/eval/*.py — see docs/evaluation.md
for the schema and how to add cases.
"""

import json
from pathlib import Path

GOLDEN_PATH = Path(__file__).parent / "golden_cases.jsonl"


def load_cases(category: str | None = None) -> list[dict]:
    cases = [json.loads(line) for line in GOLDEN_PATH.read_text(encoding="utf-8").splitlines() if line.strip()]
    if category:
        cases = [c for c in cases if c["category"] == category]
    return cases
