#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from norway_company_agent.sentiment import evaluate_predictions


def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate sentiment predictions against gold standard benchmark.")
    parser.add_argument("--gold", required=True)
    parser.add_argument("--predictions", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--minimum-items", type=int, default=300)
    args = parser.parse_args()

    gold = read_jsonl(Path(args.gold))
    predictions = read_jsonl(Path(args.predictions))
    report = evaluate_predictions(gold, predictions, minimum_items=args.minimum_items)

    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    Path(args.output).write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    raise SystemExit(0 if report["qualification_passed"] else 1)


if __name__ == "__main__":
    main()
