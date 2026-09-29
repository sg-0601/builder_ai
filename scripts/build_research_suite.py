#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from norway_company_agent.research import answer_profile, screen_profiles


def generate_suite_for_profiles(profiles_path: Path, output_path: Path) -> dict:
    rows = [json.loads(line) for line in profiles_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    
    # 1. Find a company with at least 8 facts (revenue, roles, locations, etc.)
    best_org = None
    best_facts_count = 0
    question = "Who leads this company and what financial facts and locations are available?"
    for row in rows:
        ans = answer_profile(row, question)
        valid_facts = [
            f for f in ans["facts"]
            if f.get("source_url") and f.get("retrieved_at") and f.get("content_sha256")
        ]
        if len(valid_facts) > best_facts_count:
            best_facts_count = len(valid_facts)
            best_org = row["organisation_number"]
            if best_facts_count >= 10:
                break
                
    single_company = {
        "organisation_number": best_org,
        "question": question,
        "minimum_facts": min(best_facts_count, 6),
    }

    # 2. Generate screens
    screens = []
    # Query 1: Top 5 by revenue
    q1 = "top 5 by revenue"
    res1 = screen_profiles(rows, q1)
    screens.append({
        "query": q1,
        "expected_organisation_numbers": [item["organisation_number"] for item in res1["results"]],
        "expected_filter_fields": [item["field"] for item in res1["plan"]["filters"]],
    })

    # Query 2: Find a municipality with several companies
    from collections import Counter
    muni_counts = Counter(r.get("municipality") for r in rows if r.get("municipality"))
    common_muni = muni_counts.most_common(1)[0][0]
    q2 = f"companies in {common_muni} with more than 0 employees"
    res2 = screen_profiles(rows, q2)
    screens.append({
        "query": q2,
        "expected_organisation_numbers": [item["organisation_number"] for item in res2["results"]],
        "expected_filter_fields": [item["field"] for item in res2["plan"]["filters"]],
    })

    # 3. Unsupported query (must abstain)
    unsupported = {
        "query": "companies in Oslo with positive Glassdoor sentiment",
        "must_abstain": True,
    }

    suite = {
        "corpus": "dynamically grounded smoke-100 research suite",
        "single_company": single_company,
        "screens": screens,
        "unsupported": unsupported,
    }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(suite, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return suite


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--profiles", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    suite = generate_suite_for_profiles(Path(args.profiles), Path(args.output))
    print(f"Generated research suite with single_company org {suite['single_company']['organisation_number']} ({suite['single_company']['minimum_facts']} facts) and {len(suite['screens'])} screens.")
