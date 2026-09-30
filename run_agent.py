#!/usr/bin/env python3
"""Main competition entry point for Signalpost / Builderr evaluator.

Supports standard competition invocation:
    python run_agent.py --organisations batch.txt --bulk brreg-enheter.csv --output-dir out/
    python run_agent.py entry-companies-100.jsonl
    python run_agent.py --strategy decision_table_router --dry-run
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent

# Automatically detect and include .venv site-packages if available and not yet on path
for site_pkg in (ROOT / ".venv").glob("**/site-packages"):
    if site_pkg.is_dir() and str(site_pkg) not in sys.path:
        sys.path.insert(0, str(site_pkg))

sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))


def count_organisations(org_path: Path) -> int:
    """Safely count organisation numbers in JSON, JSONL, or text file."""
    if not org_path.exists():
        return 100
    try:
        text = org_path.read_text(encoding="utf-8").strip()
        if not text:
            return 0
        if text.startswith("["):
            data = json.loads(text)
            return len(data)
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        return len(lines)
    except Exception:
        return 100


def main() -> None:
    args = sys.argv[1:]

    # 1. Routing to evaluation engine if evaluation flags are present
    if any(arg in args for arg in ("--eval", "--strategy", "--challenger", "--dry-run")):
        from eval.run import main as eval_main
        clean_args = [a for a in args if a != "--eval"]
        sys.argv = [sys.argv[0]] + clean_args
        eval_main()
        return

    # 2. Handle positional argument if provided (e.g. `python run_agent.py entry-companies-100.jsonl`)
    org_flag_present = any(arg in args for arg in ("--organisations", "--orgs", "-i"))
    if not org_flag_present:
        positional = [a for a in args if not a.startswith("-")]
        if positional:
            target_org = positional[0]
            args.remove(target_org)
            args.extend(["--organisations", target_org])
            org_flag_present = True

    # 3. Resolve target organisations file
    chosen_orgs = None
    for i, a in enumerate(args):
        if a in ("--organisations", "--orgs", "-i") and i + 1 < len(args):
            chosen_orgs = args[i + 1]
            break

    if not chosen_orgs:
        org_candidates = [
            ROOT / "entry-companies-100.jsonl",
            ROOT / "batch-100.jsonl",
            ROOT / "entry-companies.jsonl",
            ROOT / "smoke-10.jsonl",
            Path.cwd() / "entry-companies-100.jsonl",
            Path.cwd() / "batch-100.jsonl",
        ]
        chosen_orgs = next((str(p) for p in org_candidates if p.exists()), str(ROOT / "entry-companies-100.jsonl"))
        args.extend(["--organisations", chosen_orgs])

    # 4. Resolve bulk candidates (large universe or self-contained profile jsonl)
    bulk_candidates = [
        ROOT / "signalpost-company-universe-2025.jsonl.gz",
        ROOT / "brreg-enheter.csv",
        ROOT / "signalpost-universe.jsonl.gz",
        ROOT.parent / "signalpost-company-universe-2025.jsonl.gz",
        Path.cwd() / "signalpost-company-universe-2025.jsonl.gz",
        Path.cwd() / "brreg-enheter.csv",
    ]
    if chosen_orgs and Path(chosen_orgs).exists() and Path(chosen_orgs).suffix == ".jsonl":
        bulk_candidates.append(Path(chosen_orgs))

    chosen_bulk = next((str(p) for p in bulk_candidates if p.exists()), chosen_orgs)

    bulk_flag_present = any(arg in args for arg in ("--bulk", "-b"))
    if not bulk_flag_present:
        args.extend(["--bulk", chosen_bulk])
    elif "--bulk" in args:
        b_idx = args.index("--bulk")
        if b_idx + 1 < len(args) and not Path(args[b_idx + 1]).exists() and chosen_bulk and Path(chosen_bulk).exists():
            print(f"Notice: Bulk snapshot {args[b_idx + 1]} not found; using baseline {chosen_bulk}")
            args[b_idx + 1] = chosen_bulk

    # 4. Handle output directory and required batch arguments
    output_dir = "out"
    if "--output-dir" in args:
        idx = args.index("--output-dir")
        output_dir = args[idx + 1]
        args.pop(idx + 1)
        args.pop(idx)
    elif "-d" in args:
        idx = args.index("-d")
        output_dir = args[idx + 1]
        args.pop(idx + 1)
        args.pop(idx)

    out_path = Path(output_dir)
    out_path.mkdir(parents=True, exist_ok=True)

    if "--output" not in args:
        args.extend(["--output", str(out_path / "envelopes.jsonl")])
    if "--profiles-output" not in args:
        args.extend(["--profiles-output", str(out_path / "profiles.jsonl")])
    if "--report" not in args:
        args.extend(["--report", str(out_path / "report.json")])
    if "--run-id" not in args:
        args.extend(["--run-id", f"run-{int(time.time())}"])

    # 5. Dynamically detect expected count so batches of any size work without error
    if "--expected-count" not in args:
        org_file = None
        for i, a in enumerate(args):
            if a in ("--organisations", "--orgs", "-i") and i + 1 < len(args):
                org_file = Path(args[i + 1])
                break
        if org_file:
            cnt = count_organisations(org_file)
            args.extend(["--expected-count", str(cnt)])

    # 6. Check if full agent mode (all APIs: paid + free) or minimal official batch
    if any(a in args for a in ("--all-apis", "--full-agent", "--enrich-external", "--with-apis")):
        clean_args = [a for a in args if a not in ("--all-apis", "--full-agent", "--with-apis")]
        if "--enrich-external" not in clean_args:
            clean_args.append("--enrich-external")
        sys.argv = [sys.argv[0]] + clean_args
        from scripts.run_agent import main as full_agent_main
        full_agent_main()
    else:
        sys.argv = [sys.argv[0]] + args
        from scripts.run_competition_batch import main as comp_batch_main
        comp_batch_main()


if __name__ == "__main__":
    main()
