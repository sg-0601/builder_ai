from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from norway_company_agent.consensus_engine import (
    EngineVote,
    arbitrate_company_profile,
    build_raw_engine_signals,
    cross_verify_pillar,
    normalize_vote_value,
)


class TestConsensusEngine(unittest.TestCase):
    def test_normalize_vote_value(self):
        self.assertEqual(normalize_vote_value("  https://example.com/  "), "https://example.com")
        self.assertEqual(normalize_vote_value("Oslo"), "oslo")
        self.assertEqual(normalize_vote_value(100), "100")
        self.assertEqual(normalize_vote_value(None), "")

    def test_unanimous_agreement(self):
        votes = [
            EngineVote("EngineA", "free_official", "revenue", 5000000, 1.0, "https://brreg.no"),
            EngineVote("EngineB", "free_public", "revenue", 5000000, 0.95, "https://proff.no"),
            EngineVote("EngineC", "paid_commercial", "revenue", 5000000, 0.98, "https://brave.com"),
        ]
        result = cross_verify_pillar("financials", votes)
        self.assertEqual(result["status"], "available")
        self.assertEqual(result["consensus"], "unanimous_agreement")
        self.assertEqual(result["agreement_rate"], 1.0)
        self.assertEqual(result["confidence"], 1.0)
        self.assertEqual(result["resolved_value"], 5000000)
        self.assertIn("100% unanimous agreement", result["discussion"])

    def test_empty_signals(self):
        votes = [
            EngineVote("EngineA", "free_official", "vacancies", None, 0.5, "https://brreg.no"),
            EngineVote("EngineB", "free_official", "vacancies", [], 0.5, "https://nav.no"),
        ]
        result = cross_verify_pillar("hiring_and_activity", votes)
        self.assertEqual(result["status"], "not_available")
        self.assertEqual(result["consensus"], "empty_signals")
        self.assertEqual(result["agreement_rate"], 1.0)
        self.assertIn("independently cross-verified the absence of data", result["discussion"])

    def test_adjudicated_majority_financials(self):
        votes = [
            EngineVote("Brreg Official API", "free_official", "accounts", {"turnover": 1000}, 1.0, "https://data.brreg.no"),
            EngineVote("Web Commercial Estimate", "paid_commercial", "accounts", {"turnover": 1200}, 0.7, "https://web.com"),
        ]
        result = cross_verify_pillar("financials", votes)
        self.assertEqual(result["status"], "available")
        self.assertEqual(result["consensus"], "adjudicated_majority")
        self.assertEqual(result["resolved_value"], {"turnover": 1000})
        self.assertIn("Official Government Registry Engine", result["discussion"])

    def test_build_raw_engine_signals_and_arbitration(self):
        profile = {
            "organisation_number": "912345678",
            "name": "Equinor Test AS",
            "business_address": "Forusbeen 50",
            "postal_code": "4035",
            "city": "Stavanger",
            "municipality": "Stavanger",
            "employees": 20000,
            "website": "https://www.equinor.com",
            "evidence": {
                "financials": {"status": "available", "value": {"turnover": 500000000, "operating_profit": 80000000}},
                "roles": {"status": "available", "value": [{"role": "daglig leder", "name": "Anders Opedal"}]},
                "locations": {"status": "available", "value": [{"address": "Forusbeen 50"}]},
                "website": {"status": "available", "value": {"final_url": "https://www.equinor.com"}},
            },
        }
        observations = [
            {"platform": "brreg", "signal_type": "workforce_snapshot", "metrics": {"workforce_value": 20000}},
            {"platform": "job_board", "signal_type": "job_posting", "metrics": {"job_title": "Senior Engineer"}},
            {"platform": "news", "signal_type": "public_mention", "sentiment_label": "positive"},
        ]
        signals = build_raw_engine_signals(profile, observations)
        self.assertIn("financials", signals)
        self.assertIn("leadership", signals)
        self.assertIn("location", signals)
        self.assertIn("hiring_and_activity", signals)
        self.assertIn("sources_found", signals)

        summary = arbitrate_company_profile(profile, signals)
        self.assertIn("overall_agreement_rate", summary)
        self.assertIn("unanimous_pillars", summary)
        self.assertIn("arbitration_status", summary)
        self.assertIn("engine_audit", summary)
        self.assertIn("ai_council", summary)
        self.assertEqual(summary["engine_audit"]["ai_council_members"], 10)
        self.assertGreater(summary["engine_audit"]["total_votes_collected"], 20)

    def test_llm_council_deliberation(self):
        from norway_company_agent.llm_council import LLMCouncil

        council = LLMCouncil()
        self.assertEqual(len(council.members), 10)
        profile = {"organisation_number": "912345678", "name": "Equinor Test AS", "evidence": {}}
        res = council.evaluate_council(profile)
        self.assertEqual(res["council_size"], 10)
        self.assertEqual(res["engines_evaluated"], 10)
        self.assertIn("10-Engine Council deliberated", res["discussion_log"])


if __name__ == "__main__":
    unittest.main()
