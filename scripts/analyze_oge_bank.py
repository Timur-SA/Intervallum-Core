"""Analyse the OGE bank and prepare LLM review prompts.

Usage:
    python scripts/analyze_oge_bank.py
    python scripts/analyze_oge_bank.py --strict
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from intervallum_ml.v2.content import load_oge_bank
from intervallum_ml.v2.quantities import coverage_report, llm_review_prompt


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--content-dir", default="content/oge_2026")
    parser.add_argument("--out", default="content/oge_2026/llm_review.jsonl")
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()

    bank = load_oge_bank(args.content_dir)
    report = coverage_report(bank)
    report["content_ok"] = bank.ok
    report["issues"] = [
        {"severity": i.severity, "code": i.code, "message": i.message, "task_id": i.task_id}
        for i in bank.issues
    ]
    print(json.dumps(report, ensure_ascii=False, indent=2))

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8") as f:
        for task in bank.tasks.values():
            f.write(
                json.dumps(
                    {"task_id": task.id, "prompt": llm_review_prompt(task)},
                    ensure_ascii=False,
                )
                + "\n"
            )

    if not bank.ok:
        raise SystemExit(1)
    if args.strict and (report["missing_topics"] or report["tasks_without_explanation"]):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
