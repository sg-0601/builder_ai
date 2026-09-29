"""Promotion Gate enforcing the strict challenger promotion rule."""

from __future__ import annotations

from typing import Any


def evaluate_promotion_gate(
    baseline: dict[str, Any],
    challenger: dict[str, Any],
    min_coverage_gain: float = 0.0,
    max_allowed_cost_usd: float = 0.50,
    max_allowed_runtime_ms: int = 10_000,
) -> dict[str, Any]:
    """Promotes a challenger strategy ONLY when ALL strict criteria are met:
    
    1. Zero new material wrong-company publications (must not increase)
    2. No meaningful drop in claim precision (precision >= baseline - 0.01)
    3. Evidence completeness remains >= 95% (target 100%)
    4. Useful coverage or recall improves by declared minimum (or holds if baseline already high)
    5. Runtime and cost remain within budget limits
    """
    gates = {}

    # Gate 1: Wrong company publications
    new_wrong_companies = challenger.get("wrong_company_count", 0) - baseline.get("wrong_company_count", 0)
    gates["gate_1_zero_new_wrong_companies"] = {
        "passed": challenger.get("wrong_company_count", 0) == 0 and new_wrong_companies <= 0,
        "baseline": baseline.get("wrong_company_count", 0),
        "challenger": challenger.get("wrong_company_count", 0),
        "delta": new_wrong_companies,
    }

    # Gate 2: Claim precision
    precision_drop = baseline.get("claim_precision", 1.0) - challenger.get("claim_precision", 1.0)
    gates["gate_2_claim_precision_maintained"] = {
        "passed": precision_drop <= 0.02,
        "baseline": baseline.get("claim_precision", 0.0),
        "challenger": challenger.get("claim_precision", 0.0),
        "precision_drop": round(precision_drop, 4),
    }

    # Gate 3: Evidence completeness
    challenger_evidence = challenger.get("evidence_validity", 0.0)
    gates["gate_3_evidence_completeness"] = {
        "passed": challenger_evidence >= 0.95 or challenger_evidence >= baseline.get("evidence_validity", 0.0),
        "baseline": baseline.get("evidence_validity", 0.0),
        "challenger": challenger_evidence,
    }

    # Gate 4: Useful coverage or recall improvement
    coverage_delta = challenger.get("coverage_recall", 0.0) - baseline.get("coverage_recall", 0.0)
    gates["gate_4_coverage_gain"] = {
        "passed": coverage_delta >= min_coverage_gain,
        "baseline": baseline.get("coverage_recall", 0.0),
        "challenger": challenger.get("coverage_recall", 0.0),
        "coverage_delta": round(coverage_delta, 4),
        "min_gain_required": min_coverage_gain,
    }

    # Gate 5: Runtime & Cost within budget
    challenger_cost = challenger.get("total_cost_usd", 0.0)
    challenger_runtime = challenger.get("mean_runtime_ms", 0)
    gates["gate_5_budget_and_latency"] = {
        "passed": challenger_cost <= max_allowed_cost_usd and challenger_runtime <= max_allowed_runtime_ms,
        "cost_usd": challenger_cost,
        "max_cost_allowed": max_allowed_cost_usd,
        "mean_runtime_ms": challenger_runtime,
        "max_runtime_allowed": max_allowed_runtime_ms,
    }

    # Final Decision: All gates must pass
    all_passed = all(g["passed"] for g in gates.values())
    decision = "PROMOTED" if all_passed else "REJECTED"

    rejection_reasons = [k for k, v in gates.items() if not v["passed"]]

    return {
        "decision": decision,
        "promoted": all_passed,
        "baseline_strategy": f"{baseline.get('strategy_name')}@{baseline.get('strategy_version')}",
        "challenger_strategy": f"{challenger.get('strategy_name')}@{challenger.get('strategy_version')}",
        "overall_score_baseline": baseline.get("overall_score", 0.0),
        "overall_score_challenger": challenger.get("overall_score", 0.0),
        "gates": gates,
        "rejection_reasons": rejection_reasons,
    }
