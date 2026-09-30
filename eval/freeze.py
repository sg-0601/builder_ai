"""Freeze manifest generation module adhering to Section 6 of the Learning Harness.

Before Builderr selects the random daily batch, this module freezes:
1. Code and dependency lockfile (git commit, pyproject.toml hash)
2. Strategy versions and routing table
3. Prompts, models, and model versions
4. Thresholds and publication gates
5. Source allowlist and crawl/API budgets
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from norway_company_agent.discovery import BLOCKED_DISCOVERY_HOSTS
from norway_company_agent.llm_council import LLMCouncil
from strategies.registry import STRATEGY_REGISTRY


def get_git_commit() -> str:
    try:
        res = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=str(ROOT),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=3,
        )
        if res.returncode == 0:
            return res.stdout.strip()
    except Exception:
        pass
    return "uncommitted_local"


def compute_file_hash(path: Path) -> str:
    if not path.exists():
        return "missing"
    return hashlib.sha256(path.read_bytes()).hexdigest()


def compute_manifest_seal(manifest: dict[str, Any]) -> str:
    """Computes SHA-256 seal of the manifest payload (excluding the seal itself)."""
    payload = {k: v for k, v in manifest.items() if k != "integrity_seal_sha256"}
    raw_bytes = json.dumps(payload, sort_keys=True).encode("utf-8")
    return hashlib.sha256(raw_bytes).hexdigest()


def generate_freeze_manifest(frozen_at: str | None = None) -> dict[str, Any]:
    """Generates the frozen submission manifest."""
    council = LLMCouncil()

    # 1. Code and Dependency Lockfile
    pyproject_path = ROOT / "pyproject.toml"
    code_state = {
        "git_commit": get_git_commit(),
        "pyproject_sha256": compute_file_hash(pyproject_path),
        "frozen_at": frozen_at or datetime.now(timezone.utc).isoformat(),
    }

    # 2. Strategy Versions and Routing Table
    strategies_info = {}
    for name in STRATEGY_REGISTRY.list_strategies():
        strat = STRATEGY_REGISTRY.get(name)
        strategies_info[name] = {
            "name": strat.name,
            "version": strat.version,
            "class": strat.__class__.__name__,
        }

    routing_table = {
        "default_baseline": "registry_site_v1",
        "default_challenger": "browser_fallback_v2",
        "routing_policy": "decision_table",
        "decision_table_order": [
            "1. static HTML first (registry_site / static_homepage_crawl)",
            "2. browser rendering only after a JavaScript-shell test confirms need",
            "3. PDF layout parsing / annual accounts when plain text fails",
            "4. search provider discovery when official website is unlisted",
        ],
        "registered_strategies": strategies_info,
    }

    # 3. Prompts, Models, and Model Versions
    models_info = [
        {
            "name": m.name,
            "provider": m.provider,
            "tier": m.tier,
            "model_name": m.model_name,
            "active": m.has_active_key(),
        }
        for m in council.members
    ]

    # 4. Thresholds and Publication Gates
    publication_gates = {
        "wrong_company_tolerance": 0,
        "min_claim_precision": 0.95,
        "evidence_completeness_target": 1.00,
        "evidence_completeness_min": 0.95,
        "max_runtime_per_company_ms": 10000,
        "max_p95_batch_latency_ms": 10000,
        "max_cost_per_company_usd": 0.05,
        "max_cumulative_batch_budget_usd": 8.50,
    }

    # 5. Source Allowlist and Budgets
    source_allowlist = {
        "allowed_official_sources": [
            "https://data.brreg.no/enhetsregisteret/api/enheter",
            "https://data.brreg.no/regnskapsregisteret/regnskap",
            "https://arbeidsplassen.nav.no/stillinger/api",
            "https://news.google.com/rss",
            "https://www.gulesider.no/bedrifter",
        ],
        "allowed_commercial_sources": [
            "https://api.search.brave.com",
            "https://maps.googleapis.com",
            "https://places.googleapis.com",
            "https://api.tavily.com",
        ],
        "blocked_discovery_hosts": sorted(list(BLOCKED_DISCOVERY_HOSTS)),
        "budget_limits": {
            "max_requests_per_company": 12,
            "max_bytes_per_request": 2000000,
            "robots_txt_obeyed": True,
        },
    }

    manifest = {
        "freeze_version": "1.0.0",
        "code_state": code_state,
        "routing_table": routing_table,
        "models": models_info,
        "publication_gates": publication_gates,
        "source_allowlist": source_allowlist,
    }

    manifest["integrity_seal_sha256"] = compute_manifest_seal(manifest)
    return manifest


def verify_freeze_manifest(manifest_path: Path) -> tuple[bool, list[str]]:
    """Verifies existing freeze manifest against current system state."""
    if not manifest_path.exists():
        return False, [f"Manifest file not found: {manifest_path}"]

    try:
        existing = json.loads(manifest_path.read_text(encoding="utf-8"))
    except Exception as e:
        return False, [f"Failed to parse manifest JSON: {e}"]

    # 1. Verify cryptographic seal integrity
    expected_seal = compute_manifest_seal(existing)
    recorded_seal = existing.get("integrity_seal_sha256")
    if expected_seal != recorded_seal:
        return False, ["Cryptographic integrity seal mismatch: Manifest file has been tampered with!"]

    # 2. Compare system configuration (strategies, routing, models, gates, allowlists)
    current = generate_freeze_manifest(frozen_at=existing.get("code_state", {}).get("frozen_at"))
    diffs = []

    # Check code state
    if existing.get("code_state", {}).get("pyproject_sha256") != current.get("code_state", {}).get("pyproject_sha256"):
        diffs.append("Dependencies changed (pyproject.toml modified)")

    # Check strategies and routing table
    if existing.get("routing_table") != current.get("routing_table"):
        diffs.append("Routing table or strategy registry modified")

    # Check models and prompts
    if existing.get("models") != current.get("models"):
        diffs.append("Model configurations or active keys modified")

    # Check publication gates
    if existing.get("publication_gates") != current.get("publication_gates"):
        diffs.append("Publication gates or thresholds modified")

    # Check source allowlist
    if existing.get("source_allowlist") != current.get("source_allowlist"):
        diffs.append("Source allowlist or budgets modified")

    return (len(diffs) == 0), diffs


def save_freeze_manifest(output_path: Path | None = None) -> Path:
    target = output_path or (ROOT / "freeze_manifest.json")
    manifest = generate_freeze_manifest()
    target.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return target


def main() -> None:
    parser = argparse.ArgumentParser(description="Signalpost Evaluation Freeze Manifest Generator")
    parser.add_argument("--output", default="freeze_manifest.json", help="Output path for freeze manifest")
    parser.add_argument("--verify", action="store_true", help="Verify existing freeze manifest against current system")
    args = parser.parse_args()

    out_path = ROOT / args.output if not Path(args.output).is_absolute() else Path(args.output)
    if args.verify:
        passed, diffs = verify_freeze_manifest(out_path)
        if passed:
            print("[OK] Freeze manifest is INTACT and matches current system configuration.")
        else:
            print("[!] Freeze manifest DIFFERENCE detected! System has mutated since last freeze:")
            for d in diffs:
                print(f"    - {d}")
            print("\nTo update the freeze manifest with your latest changes, run:")
            print("    python -m eval.freeze")
    else:
        saved_path = save_freeze_manifest(out_path)
        print(f"[OK] Signalpost Daily Evaluation Freeze Manifest generated and saved to: {saved_path}")


if __name__ == "__main__":
    main()
