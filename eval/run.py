"""CLI runner executing the complete evaluation and promotion loop.

Command:
    python -m eval.run --corpus eval/gold_companies.jsonl --challenger browser_fallback_v2
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from dotenv import load_dotenv
load_dotenv(ROOT / ".env")

from eval.promotion_gate import evaluate_promotion_gate
from eval.score_attempts import score_strategy_attempts
from strategies.registry import STRATEGY_REGISTRY


def load_corpus(path: Path) -> list[dict]:
    companies = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                companies.append(json.loads(line))
    return companies


def save_attempts(attempts: list, storage_dir: Path, tag: str) -> None:
    storage_dir.mkdir(parents=True, exist_ok=True)
    out_file = storage_dir / f"attempts_{tag}_{int(datetime.now().timestamp())}.jsonl"
    with open(out_file, "w", encoding="utf-8") as f:
        for att in attempts:
            f.write(json.dumps(att.to_dict(), default=str) + "\n")


def save_claims(attempts: list, storage_dir: Path, tag: str) -> None:
    storage_dir.mkdir(parents=True, exist_ok=True)
    out_file = storage_dir / f"claims_{tag}_{int(datetime.now().timestamp())}.jsonl"
    with open(out_file, "w", encoding="utf-8") as f:
        for att in attempts:
            for c in att.claims:
                claim_data = c.to_dict() if hasattr(c, "to_dict") else c
                claim_data["organisation_number"] = att.organisation_number
                claim_data["strategy"] = att.strategy_name
                f.write(json.dumps(claim_data, default=str) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser(description="Signalpost Learning Harness - Evaluation & Promotion Loop")
    parser.add_argument("--corpus", default="eval/gold_companies.jsonl", help="Path to evaluation corpus JSONL")
    parser.add_argument("--challenger", required=True, help="Name of challenger strategy to evaluate")
    parser.add_argument("--baseline", default="registry_site", help="Name of baseline strategy to compare against")
    parser.add_argument("--min-gain", type=float, default=0.0, help="Minimum coverage gain required to promote")
    args = parser.parse_args()

    corpus_path = ROOT / args.corpus if not Path(args.corpus).is_absolute() else Path(args.corpus)
    if not corpus_path.exists():
        print(f"[!] Error: Corpus file not found: {corpus_path}")
        sys.exit(1)

    companies = load_corpus(corpus_path)
    gold_map = {str(c.get("organisation_number")): c for c in companies}

    # Resolve strategies from registry
    try:
        baseline_strat = STRATEGY_REGISTRY.get(args.baseline)
    except KeyError:
        print(f"[!] Baseline '{args.baseline}' not in registry. Using 'registry_site'.")
        baseline_strat = STRATEGY_REGISTRY.get("registry_site")

    try:
        challenger_strat = STRATEGY_REGISTRY.get(args.challenger)
    except KeyError as exc:
        print(f"[!] Error: {exc}")
        sys.exit(1)

    print("=" * 70)
    print("SIGNALPOST LEARNING HARNESS — STRATEGY EVALUATION LOOP")
    print("=" * 70)
    print(f"Corpus:     {args.corpus} ({len(companies)} companies)")
    print(f"Baseline:   {baseline_strat.name} (v{baseline_strat.version})")
    print(f"Challenger: {challenger_strat.name} (v{challenger_strat.version})")
    print("-" * 70)

    # 1. Execute Baseline
    print(f"[*] Running baseline strategy: {baseline_strat.name}...")
    baseline_attempts = [baseline_strat.execute(c) for c in companies]

    # 2. Execute Challenger
    print(f"[*] Running challenger strategy: {challenger_strat.name}...")
    challenger_attempts = [challenger_strat.execute(c) for c in companies]

    # 3. Preserve Every Attempt & Claim (Snapshots & Claims storage)
    save_attempts(baseline_attempts, ROOT / "snapshots", baseline_strat.name)
    save_attempts(challenger_attempts, ROOT / "snapshots", challenger_strat.name)
    save_claims(baseline_attempts, ROOT / "claims", baseline_strat.name)
    save_claims(challenger_attempts, ROOT / "claims", challenger_strat.name)
    print("[*] Saved snapshots and claims to snapshots/ and claims/ directories.")

    # 4. Score in Strict Order
    baseline_score = score_strategy_attempts(baseline_attempts, gold_map)
    challenger_score = score_strategy_attempts(challenger_attempts, gold_map)

    # 5. Apply Promotion Gate
    gate_result = evaluate_promotion_gate(
        baseline_score,
        challenger_score,
        min_coverage_gain=args.min_gain,
    )

    # 6. Save Comparison Report
    reports_dir = ROOT / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    report_file = reports_dir / f"comparison_{challenger_strat.name}_{int(datetime.now().timestamp())}.json"
    full_report = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "corpus": str(args.corpus),
        "baseline_score": baseline_score,
        "challenger_score": challenger_score,
        "promotion_gate": gate_result,
    }
    with open(report_file, "w", encoding="utf-8") as f:
        json.dump(full_report, f, indent=2)

    # 7. Print Human-Readable Summary
    print("\n" + "=" * 70)
    print("EVALUATION & PROMOTION REPORT")
    print("=" * 70)
    print(f"{'METRIC':<30} | {'BASELINE':<16} | {'CHALLENGER':<16}")
    print("-" * 70)
    print(f"{'Strategy Name':<30} | {baseline_score['strategy_name']:<16} | {challenger_score['strategy_name']:<16}")
    print(f"{'Strategy Version':<30} | {baseline_score['strategy_version']:<16} | {challenger_score['strategy_version']:<16}")
    print(f"{'Wrong-Company Pubs':<30} | {baseline_score['wrong_company_count']:<16} | {challenger_score['wrong_company_count']:<16}")
    print(f"{'Claim Precision':<30} | {baseline_score['claim_precision']*100:<15.1f}% | {challenger_score['claim_precision']*100:<15.1f}%")
    print(f"{'Evidence Validity':<30} | {baseline_score['evidence_validity']*100:<15.1f}% | {challenger_score['evidence_validity']*100:<15.1f}%")
    print(f"{'Coverage / Recall':<30} | {baseline_score['coverage_recall']:<16.2f} | {challenger_score['coverage_recall']:<16.2f}")
    print(f"{'Mean Runtime (ms)':<30} | {baseline_score['mean_runtime_ms']:<16} | {challenger_score['mean_runtime_ms']:<16}")
    print(f"{'Mean Requests':<30} | {baseline_score['mean_request_count']:<16.2f} | {challenger_score['mean_request_count']:<16.2f}")
    print(f"{'Total Cost ($)':<30} | ${baseline_score['total_cost_usd']:<15.4f} | ${challenger_score['total_cost_usd']:<15.4f}")
    print(f"{'OVERALL SCORE':<30} | {baseline_score['overall_score']:<15.1f}/100 | {challenger_score['overall_score']:<15.1f}/100")
    print("-" * 70)

    print("\nPROMOTION GATES:")
    for gate_name, gate in gate_result["gates"].items():
        status = "PASSED [OK]" if gate["passed"] else "FAILED [X]"
        print(f"  * {gate_name:<36} : {status}")

    print("\n" + "=" * 70)
    decision = gate_result["decision"]
    if decision == "PROMOTED":
        print(f"VERDICT: >>> PROMOTED <<< ({challenger_strat.name} is the new production winner!)")
    else:
        print(f"VERDICT: >>> REJECTED <<< (Reasons: {', '.join(gate_result['rejection_reasons'])})")
    print(f"Full report saved to: {report_file}")
    print("=" * 70)


if __name__ == "__main__":
    main()
