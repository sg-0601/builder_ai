"""CLI runner executing the complete evaluation and promotion loop.

Commands for PowerShell:
    # Compare challenger against baseline (saving snapshots & report):
    python -m eval.run --challenger browser_fallback_v2

    # Measure accuracy without modifying any folders (dry-run):
    python -m eval.run --challenger browser_fallback_v2 --dry-run

    # Evaluate a single strategy without modifying any folders:
    python -m eval.run --strategy decision_table_router --dry-run
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


from concurrent.futures import ThreadPoolExecutor, as_completed


def run_strategy_concurrent(strategy, company_list: list[dict], max_workers: int = 8) -> list:
    if max_workers <= 1 or len(company_list) <= 1:
        return [strategy.execute(c) for c in company_list]
    with ThreadPoolExecutor(max_workers=min(max_workers, len(company_list))) as pool:
        future_to_idx = {pool.submit(strategy.execute, c): i for i, c in enumerate(company_list)}
        results = [None] * len(company_list)
        for future in as_completed(future_to_idx):
            idx = future_to_idx[future]
            results[idx] = future.result()
        return results


def main() -> None:
    parser = argparse.ArgumentParser(description="Signalpost Learning Harness - Strategy Evaluation & Accuracy Runner")
    parser.add_argument("--corpus", default="eval/gold_companies.jsonl", help="Path to evaluation corpus JSONL")
    parser.add_argument("--strategy", default=None, help="Name of strategy to evaluate individually")
    parser.add_argument("--challenger", default=None, help="Name of challenger strategy to compare against baseline")
    parser.add_argument("--baseline", default="registry_site", help="Name of baseline strategy (default: registry_site)")
    parser.add_argument("--min-gain", type=float, default=0.0, help="Minimum coverage gain required to promote")
    parser.add_argument("--workers", type=int, default=8, help="Number of concurrent workers (default: 8)")
    parser.add_argument("--dry-run", "--no-save", dest="dry_run", action="store_true", help="Run in memory without saving any files or snapshots to folder")
    args = parser.parse_args()

    # Determine execution mode: single strategy or challenger-vs-baseline comparison
    target_strategy = args.strategy or args.challenger
    if not target_strategy:
        target_strategy = "decision_table_router"

    corpus_path = ROOT / args.corpus if not Path(args.corpus).is_absolute() else Path(args.corpus)
    if not corpus_path.exists():
        print(f"[!] Error: Corpus file not found: {corpus_path}")
        sys.exit(1)

    companies = load_corpus(corpus_path)
    gold_map = {str(c.get("organisation_number")): c for c in companies}

    # Resolve target strategy
    try:
        strat = STRATEGY_REGISTRY.get(target_strategy)
    except KeyError as exc:
        print(f"[!] Error: {exc}")
        sys.exit(1)

    # Resolve baseline if comparison requested
    is_comparison = bool(args.challenger)
    baseline_strat = None
    if is_comparison:
        try:
            baseline_strat = STRATEGY_REGISTRY.get(args.baseline)
        except KeyError:
            baseline_strat = STRATEGY_REGISTRY.get("registry_site")

    print("=" * 70)
    print("SIGNALPOST LEARNING HARNESS - STRATEGY EVALUATION LOOP")
    print("=" * 70)
    print(f"Corpus:     {args.corpus} ({len(companies)} companies)")
    if is_comparison and baseline_strat:
        print(f"Baseline:   {baseline_strat.name} (v{baseline_strat.version})")
        print(f"Challenger: {strat.name} (v{strat.version})")
    else:
        print(f"Strategy:   {strat.name} (v{strat.version})")
    print(f"Mode:       {'DRY-RUN (Read-Only / No Folder Changes)' if args.dry_run else 'PERSISTENT (Snapshots & Claims Saved)'}")
    print(f"Workers:    {args.workers} concurrent threads")
    print("-" * 70)

    # 1. Execute Target Strategy
    print(f"[*] Running strategy: {strat.name} ({args.workers} workers)...")
    attempts = run_strategy_concurrent(strat, companies, max_workers=args.workers)

    # 2. Execute Baseline if comparison requested
    baseline_attempts = None
    if is_comparison and baseline_strat:
        print(f"[*] Running baseline strategy: {baseline_strat.name} ({args.workers} workers)...")
        baseline_attempts = run_strategy_concurrent(baseline_strat, companies, max_workers=args.workers)

    # 3. Preserve Every Attempt & Claim ONLY if not dry-run
    if not args.dry_run:
        save_attempts(attempts, ROOT / "snapshots", strat.name)
        save_claims(attempts, ROOT / "claims", strat.name)
        if baseline_attempts and baseline_strat:
            save_attempts(baseline_attempts, ROOT / "snapshots", baseline_strat.name)
            save_claims(baseline_attempts, ROOT / "claims", baseline_strat.name)
        print("[*] Saved snapshots and claims to snapshots/ and claims/ directories.")
    else:
        print("[*] Dry-run active: Skipping snapshots and claims storage (zero folder changes).")

    # 4. Score in Strict Organizer Order
    strat_score = score_strategy_attempts(attempts, gold_map)
    baseline_score = score_strategy_attempts(baseline_attempts, gold_map) if baseline_attempts else None

    # 5. Evaluate Promotion Gate if comparison requested
    gate_result = None
    if is_comparison and baseline_score:
        gate_result = evaluate_promotion_gate(
            baseline_score,
            strat_score,
            min_coverage_gain=args.min_gain,
        )

    # 6. Save Comparison Report ONLY if not dry-run
    report_file = None
    if not args.dry_run:
        reports_dir = ROOT / "reports"
        reports_dir.mkdir(parents=True, exist_ok=True)
        report_file = reports_dir / f"comparison_{strat.name}_{int(datetime.now().timestamp())}.json"
        full_report = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "corpus": str(args.corpus),
            "strategy_score": strat_score,
            "baseline_score": baseline_score,
            "promotion_gate": gate_result,
        }
        with open(report_file, "w", encoding="utf-8") as f:
            json.dump(full_report, f, indent=2)

    # 7. Print Clean, Clear Accuracy & Performance Report
    print("\n" + "=" * 70)
    print("ACCURACY & EVALUATION REPORT")
    print("=" * 70)

    if is_comparison and baseline_score and gate_result:
        print(f"{'METRIC':<30} | {'BASELINE':<16} | {'CHALLENGER':<16}")
        print("-" * 70)
        print(f"{'Strategy Name':<30} | {baseline_score['strategy_name']:<16} | {strat_score['strategy_name']:<16}")
        print(f"{'Strategy Version':<30} | {baseline_score['strategy_version']:<16} | {strat_score['strategy_version']:<16}")
        print(f"{'Wrong-Company Pubs':<30} | {baseline_score['wrong_company_count']:<16} | {strat_score['wrong_company_count']:<16}")
        print(f"{'Claim Precision / Accuracy':<30} | {baseline_score['claim_precision']*100:<15.1f}% | {strat_score['claim_precision']*100:<15.1f}%")
        print(f"{'Evidence Validity':<30} | {baseline_score['evidence_validity']*100:<15.1f}% | {strat_score['evidence_validity']*100:<15.1f}%")
        print(f"{'Coverage / Recall':<30} | {baseline_score['coverage_recall']:<16.2f} | {strat_score['coverage_recall']:<16.2f}")
        print(f"{'Refresh Correctness':<30} | {baseline_score['refresh_correctness']*100:<15.1f}% | {strat_score['refresh_correctness']*100:<15.1f}%")
        print(f"{'Mean Runtime (ms)':<30} | {baseline_score['mean_runtime_ms']:<16} | {strat_score['mean_runtime_ms']:<16}")
        print(f"{'Mean Requests':<30} | {baseline_score['mean_request_count']:<16.2f} | {strat_score['mean_request_count']:<16.2f}")
        print(f"{'Total Cost ($)':<30} | ${baseline_score['total_cost_usd']:<15.4f} | ${strat_score['total_cost_usd']:<15.4f}")
        print(f"{'OVERALL SCORE':<30} | {baseline_score['overall_score']:<15.1f}/100 | {strat_score['overall_score']:<15.1f}/100")
        print("-" * 70)

        print("\nPROMOTION GATES:")
        for gate_name, gate in gate_result["gates"].items():
            status = "PASSED [OK]" if gate["passed"] else "FAILED [X]"
            print(f"  * {gate_name:<36} : {status}")

        print("\n" + "=" * 70)
        decision = gate_result["decision"]
        if decision == "PROMOTED":
            print(f"VERDICT: >>> PROMOTED <<< ({strat.name} is the new production winner!)")
        else:
            print(f"VERDICT: >>> REJECTED <<< (Reasons: {', '.join(gate_result['rejection_reasons'])})")
    else:
        print(f"{'Strategy Name:':<30} {strat_score['strategy_name']}")
        print(f"{'Strategy Version:':<30} {strat_score['strategy_version']}")
        print(f"{'Companies Evaluated:':<30} {strat_score['total_companies']}")
        print(f"{'OVERALL SCORE:':<30} {strat_score['overall_score']:.1f} / 100")
        print(f"{'Claim Precision / Accuracy:':<30} {strat_score['claim_precision']*100:.1f}%")
        print(f"{'Evidence Validity:':<30} {strat_score['evidence_validity']*100:.1f}%")
        print(f"{'Coverage / Recall:':<30} {strat_score['coverage_recall']:.2f}")
        print(f"{'Refresh Correctness:':<30} {strat_score['refresh_correctness']*100:.1f}%")
        print(f"{'Wrong-Company Count:':<30} {strat_score['wrong_company_count']} (Zero-tolerance cliff)")
        print(f"{'Mean Runtime:':<30} {strat_score['mean_runtime_ms']} ms")
        print(f"{'Mean Requests:':<30} {strat_score['mean_request_count']:.2f}")
        print(f"{'Total Cost:':<30} ${strat_score['total_cost_usd']:.4f}")
        print("=" * 70)

    if args.dry_run:
        print("\n[OK] DRY-RUN SUCCESSFUL: No files were created or modified in any folder.")
    elif report_file:
        print(f"\n[OK] Full report saved to: {report_file}")
    print("=" * 70)


if __name__ == "__main__":
    main()
