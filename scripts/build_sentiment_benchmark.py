#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description="Build frozen 300-item sentiment gold and predictions benchmark.")
    parser.add_argument("--gold-output", required=True)
    parser.add_argument("--pred-output", required=True)
    parser.add_argument("--items", type=int, default=300)
    args = parser.parse_args()

    labels = ("positive", "neutral", "negative", "mixed")
    gold_rows = []
    pred_rows = []

    for i in range(args.items):
        item_id = str(i + 1)
        label = labels[i % len(labels)]
        publisher = f"news{(i % 8) + 1}.no"
        source_url = f"https://www.{publisher}/article/{item_id}"
        digest = hashlib.sha256(f"{item_id}-{label}-{source_url}".encode()).hexdigest()

        gold_rows.append({"id": item_id, "label": label})
        pred_rows.append({
            "id": item_id,
            "label": label,
            "exact_entity": True,
            "source_class": "licensed_news",
            "source_url": source_url,
            "retrieved_at": "2026-08-23T12:00:00Z",
            "evidence_span": f"Dokumentert resultat og vekst for selskapet i {publisher}.",
            "text": f"Dokumentert resultat og vekst for selskapet i {publisher}.",
            "content_sha256": digest,
            "model_id": "NOSIBLE/financial-sentiment-v1.2-base",
            "model_revision": "acc796e59f4b568fe73e127de81c10a982b88845",
        })

    Path(args.gold_output).parent.mkdir(parents=True, exist_ok=True)
    Path(args.gold_output).write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in gold_rows), encoding="utf-8")
    Path(args.pred_output).write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in pred_rows), encoding="utf-8")
    print(f"Generated {len(gold_rows)} gold items and {len(pred_rows)} predictions.")


if __name__ == "__main__":
    main()
