"""Unit tests for the Signalpost Learning Harness and Strategy Registry."""

import pytest
from strategies.base import Claim, StrategyAttempt
from strategies.registry import STRATEGY_REGISTRY
from eval.score_attempts import score_strategy_attempts
from eval.promotion_gate import evaluate_promotion_gate
from eval.freeze import generate_freeze_manifest
from norway_company_agent.refresh import apply_safe_refresh, classify_change_type


def test_strategy_registry_discovery():
    """All 9 routes and the decision table router must be discoverable."""
    strategies = STRATEGY_REGISTRY.list_strategies()
    assert "registry_site" in strategies
    assert "sitemap_static" in strategies
    assert "static_homepage_crawl" in strategies
    assert "targeted_paths" in strategies
    assert "jsonld_opengraph" in strategies
    assert "search_candidates" in strategies
    assert "leader_founder_bridge" in strategies
    assert "browser_fallback_v1" in strategies
    assert "browser_fallback_v2" in strategies
    assert "pdf_fallback" in strategies
    assert "decision_table_router" in strategies


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


def test_freeze_manifest_integrity():
    manifest = generate_freeze_manifest()
    assert "code_state" in manifest
    assert "routing_table" in manifest
    assert "models" in manifest
    assert "publication_gates" in manifest
    assert "source_allowlist" in manifest
    assert "integrity_seal_sha256" in manifest
    assert len(manifest["integrity_seal_sha256"]) == 64


def test_refresh_typed_changes_and_non_erasure():
    # Test typed change classification
    assert classify_change_type("roles.roles", [], [{"name": "Ola Nordmann"}]) == "new_role"
    assert classify_change_type("locations.locations", [], [{"name": "Bergen Filial"}]) == "new_location"
    assert classify_change_type("financials.records", [], [{"year": "2024"}]) == "new_filing"
    assert classify_change_type("website.description", "Old desc", "New desc") == "changed_description"

    # Test non-erasure contract: failed refresh preserves previous supported data
    previous = {
        "organisation_number": "123456789",
        "evidence": {
            "financials": {
                "status": "available",
                "value": {"revenue": 1000000},
                "retrieved_at": "2026-01-01T00:00:00Z",
            }
        }
    }
    failed_refresh = {
        "organisation_number": "123456789",
        "evidence": {
            "financials": {
                "status": "source_error",
                "value": None,
                "note": "HTTP 500 upstream gateway timeout",
                "retrieved_at": "2026-09-30T00:00:00Z",
            }
        }
    }
    merged, changes = apply_safe_refresh(previous, failed_refresh)
    # Value must NOT have been erased!
    assert merged["evidence"]["financials"]["status"] == "available"
    assert merged["evidence"]["financials"]["value"] == {"revenue": 1000000}
    assert merged["evidence"]["financials"]["refresh_error"] == "HTTP 500 upstream gateway timeout"
