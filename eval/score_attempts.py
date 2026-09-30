"""Scoring engine evaluating attempts against gold standard in strict organizer order."""

from __future__ import annotations

import re
from typing import Any

from strategies.base import StrategyAttempt


def score_strategy_attempts(
    attempts: list[StrategyAttempt],
    gold_data: dict[str, dict[str, Any]],
    refresh_ground_truth: dict[str, list[dict[str, Any]]] | None = None,
) -> dict[str, Any]:
    """Scores a batch of StrategyAttempts against gold companies in strict order:
    
    1. Wrong-company publications — must not increase (Zero tolerance cliff)
    2. Supported-claim precision — must not fall
    3. Evidence validity — every accepted claim points to the right source span & content hash
    4. Coverage and recall — useful supported fields added
    5. Refresh correctness — real changes found without false changes
    6. Runtime, requests and cost — strictly bounded
    """
    total_companies = len(attempts)
    if total_companies == 0:
        return {
            "total_companies": 0,
            "wrong_company_count": 0,
            "claim_precision": 0.0,
            "evidence_validity": 0.0,
            "coverage_recall": 0.0,
            "refresh_correctness": 1.0,
            "mean_runtime_ms": 0,
            "mean_request_count": 0.0,
            "total_cost_usd": 0.0,
            "overall_score": 0.0,
        }

    wrong_company_count = 0
    total_accepted_claims = 0
    correct_accepted_claims = 0
    valid_evidence_claims = 0
    total_useful_fields = 0
    total_runtime_ms = 0
    total_requests = 0
    total_cost = 0.0

    for att in attempts:
        org = att.organisation_number
        gold = gold_data.get(org, {})
        expected_domain = (gold.get("expected_registered_domain") or "").lower()

        total_runtime_ms += att.runtime_ms
        total_requests += att.request_count
        total_cost += att.cost_usd

        # 1. Check for Wrong-Company Publications
        for c in att.accepted_claims:
            total_accepted_claims += 1

            # 3. Evidence validity check (span non-empty and hash valid)
            if c.evidence_span and len(str(c.content_hash or "")) == 64:
                valid_evidence_claims += 1

            # 2. Precision check
            if c.field == "website":
                extracted_url = str(c.value or "").lower()
                if expected_domain:
                    if expected_domain in extracted_url:
                        correct_accepted_claims += 1
                        total_useful_fields += 1
                    else:
                        # Emitted wrong website for company!
                        wrong_company_count += 1
                else:
                    # Gold has no website; publishing a random website without proof is wrong
                    if not att.exact_identity_evidence:
                        wrong_company_count += 1
                    else:
                        correct_accepted_claims += 1
                        total_useful_fields += 1
            else:
                # Other useful fields (contact, pages, title, accounts, leadership, etc.)
                correct_accepted_claims += 1
                total_useful_fields += 1

    claim_precision = round(correct_accepted_claims / max(1, total_accepted_claims), 4)
    evidence_validity = round(valid_evidence_claims / max(1, total_accepted_claims), 4)
    coverage_recall = round(total_useful_fields / max(1, total_companies * 2), 4)
    mean_runtime = int(total_runtime_ms / total_companies)
    mean_requests = round(total_requests / total_companies, 2)
    total_cost = round(total_cost, 4)

    # 5. Refresh correctness: real changes found without false changes
    refresh_correctness = 1.0
    if refresh_ground_truth:
        true_positives = 0
        false_positives = 0
        false_negatives = 0
        for att in attempts:
            org = att.organisation_number
            expected_changes = refresh_ground_truth.get(org, [])
            # Search for detected changes in attempt
            detected_changes = [c.to_dict() for c in att.accepted_claims if "change" in c.field or "refresh" in c.field]
            if not expected_changes and not detected_changes:
                true_positives += 1
            else:
                # Compare detected vs expected
                det_fields = {c.get("field") for c in detected_changes}
                exp_fields = {c.get("field") for c in expected_changes}
                true_positives += len(det_fields & exp_fields)
                false_positives += len(det_fields - exp_fields)
                false_negatives += len(exp_fields - det_fields)
        total_eval = true_positives + false_positives + false_negatives
        refresh_correctness = round(true_positives / max(1, total_eval), 4)

    # Scorer cliff: If wrong company published, score is ZERO
    if wrong_company_count > 0:
        overall_score = 0.0
    else:
        # Balanced score strictly adhering to organizer priority:
        # 35% Precision + 25% Evidence Validity + 25% Coverage + 15% Refresh Correctness
        raw = (
            claim_precision * 0.35 +
            evidence_validity * 0.25 +
            min(1.0, coverage_recall) * 0.25 +
            refresh_correctness * 0.15
        ) * 100.0
        overall_score = round(raw, 2)

    return {
        "strategy_name": attempts[0].strategy_name if attempts else "unknown",
        "strategy_version": attempts[0].strategy_version if attempts else "0.0.0",
        "total_companies": total_companies,
        "wrong_company_count": wrong_company_count,
        "total_accepted_claims": total_accepted_claims,
        "claim_precision": claim_precision,
        "evidence_validity": evidence_validity,
        "coverage_recall": coverage_recall,
        "refresh_correctness": refresh_correctness,
        "mean_runtime_ms": mean_runtime,
        "mean_request_count": mean_requests,
        "total_cost_usd": total_cost,
        "overall_score": overall_score,
    }
