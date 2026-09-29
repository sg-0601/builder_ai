"""Unit tests for the Signalpost Learning Harness and Strategy Registry."""

import pytest
from strategies.base import Claim, StrategyAttempt
from strategies.registry import STRATEGY_REGISTRY
from eval.score_attempts import score_strategy_attempts
from eval.promotion_gate import evaluate_promotion_gate


def test_strategy_registry_discovery():
    strategies = STRATEGY_REGISTRY.list_strategies()
    assert "registry_site" in strategies
    assert "sitemap_static" in strategies
    assert "targeted_paths" in strategies
    assert "search_candidates" in strategies
    assert "browser_fallback_v1" in strategies
    assert "browser_fallback_v2" in strategies
    assert "pdf_fallback" in strategies


def test_strategy_execution_and_attempt_provenance():
    strat = STRATEGY_REGISTRY.get("registry_site")
    test_company = {
        "organisation_number": "888567232",
        "name": "AAS ELEKTRONIKK AS",
        "website": "www.aelektronikk.no",
    }
    attempt = strat.execute(test_company)
    assert attempt.strategy_name == "registry_site"
    assert attempt.organisation_number == "888567232"
    assert isinstance(attempt.runtime_ms, int)
    assert attempt.runtime_ms >= 0
    assert isinstance(attempt.claims, list)
    dict_repr = attempt.to_dict()
    assert "requested_urls" in dict_repr
    assert "raw_snapshot_hashes" in dict_repr


def test_scoring_order_wrong_company_penalty():
    # Attempt with wrong company publication
    bad_attempt = StrategyAttempt(
        strategy_name="bad_strategy",
        strategy_version="1.0.0",
        organisation_number="999999999",
    )
    bad_attempt.record_claim(Claim(
        field="website",
        value="https://totallywrongcompany.com",
        confidence=0.99,
        evidence_span="fake claim",
        content_hash="a" * 64,
        source_url="https://totallywrongcompany.com",
        status="accepted",
    ))

    gold = {"999999999": {"expected_registered_domain": "actualcompany.no"}}
    score = score_strategy_attempts([bad_attempt], gold)
    assert score["wrong_company_count"] == 1
    # Penalty cliff: Score MUST be 0.0
    assert score["overall_score"] == 0.0


def test_promotion_gate_decision_rule():
    baseline = {
        "strategy_name": "baseline_v1",
        "strategy_version": "1.0.0",
        "wrong_company_count": 0,
        "claim_precision": 0.98,
        "evidence_validity": 1.0,
        "coverage_recall": 0.50,
        "mean_runtime_ms": 1200,
        "total_cost_usd": 0.01,
        "overall_score": 85.0,
    }

    # Successful challenger
    challenger_pass = {
        "strategy_name": "challenger_v2",
        "strategy_version": "2.0.0",
        "wrong_company_count": 0,
        "claim_precision": 0.99,
        "evidence_validity": 1.0,
        "coverage_recall": 0.65,
        "mean_runtime_ms": 900,
        "total_cost_usd": 0.01,
        "overall_score": 92.0,
    }
    res_pass = evaluate_promotion_gate(baseline, challenger_pass, min_coverage_gain=0.05)
    assert res_pass["decision"] == "PROMOTED"
    assert res_pass["promoted"] is True

    # Regressed challenger (wrong company introduced)
    challenger_regress = {
        "strategy_name": "challenger_v2",
        "strategy_version": "2.0.0",
        "wrong_company_count": 1,
        "claim_precision": 0.90,
        "evidence_validity": 1.0,
        "coverage_recall": 0.80,
        "mean_runtime_ms": 900,
        "total_cost_usd": 0.01,
        "overall_score": 0.0,
    }
    res_fail = evaluate_promotion_gate(baseline, challenger_regress)
    assert res_fail["decision"] == "REJECTED"
    assert res_fail["promoted"] is False
    assert "gate_1_zero_new_wrong_companies" in res_fail["rejection_reasons"]
