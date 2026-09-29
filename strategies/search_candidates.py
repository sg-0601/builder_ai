"""Search-provider candidate discovery strategy (search_candidates_v1)."""

from __future__ import annotations

import hashlib
import json
import os
import re
import urllib.parse
import urllib.request
from typing import Any

from strategies.base import BaseStrategy, Claim, StrategyAttempt

UA_HEADER = "SignalpostResearch/1.0 (+https://builderr.ai; Norwegian company research agent)"


class SearchCandidatesStrategy(BaseStrategy):
    name = "search_candidates"
    version = "1.0.0"

    def _run(self, company: dict[str, Any], attempt: StrategyAttempt, **kwargs: Any) -> None:
        org = str(company.get("organisation_number") or "")
        name = str(company.get("name") or "")
        muni = str(company.get("municipality") or "")

        tavily_key = os.getenv("TAVILY_API_KEY", "").strip()
        google_key = os.getenv("GOOGLE_PLACES_API_KEY", "").strip()

        candidate_url: str | None = None
        candidate_title: str = ""
        evidence_source: str = ""

        # Option A: Try Tavily AI Search if key is available
        if tavily_key:
            attempt.request_count += 1
            attempt.cost_usd += 0.001
            try:
                url = "https://api.tavily.com/search"
                payload = json.dumps({
                    "api_key": tavily_key,
                    "query": f'"{name}" norge orgnr {org}',
                    "search_depth": "basic",
                    "max_results": 2,
                }).encode("utf-8")
                req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json", "User-Agent": UA_HEADER})
                with urllib.request.urlopen(req, timeout=5.0) as resp:
                    data = json.loads(resp.read().decode())
                results = data.get("results", [])
                if results:
                    top = results[0]
                    candidate_url = top.get("url")
                    candidate_title = top.get("title") or ""
                    evidence_source = "tavily_ai_search"
            except Exception as e:
                attempt.errors.append(f"Tavily search failed: {str(e)[:100]}")

        # Option B: Fallback to Google Places New API if Tavily didn't yield candidate
        if not candidate_url and google_key:
            attempt.request_count += 1
            attempt.cost_usd += 0.017
            try:
                url = "https://places.googleapis.com/v1/places:searchText"
                payload = json.dumps({"textQuery": f"{name} {muni} Norway"}).encode("utf-8")
                req = urllib.request.Request(
                    url,
                    data=payload,
                    headers={
                        "Content-Type": "application/json",
                        "X-Goog-Api-Key": google_key,
                        "X-Goog-FieldMask": "places.displayName,places.formattedAddress,places.id",
                        "User-Agent": UA_HEADER,
                    },
                )
                with urllib.request.urlopen(req, timeout=5.0) as resp:
                    data = json.loads(resp.read().decode())
                places = data.get("places", [])
                if places:
                    top = places[0]
                    place_id = top.get("id")
                    candidate_url = f"https://www.google.com/maps/place/?q=place_id:{place_id}"
                    candidate_title = (top.get("displayName") or {}).get("text") or name
                    evidence_source = "google_places_api_new"
            except Exception as e:
                attempt.errors.append(f"Google places failed: {str(e)[:100]}")

        if not candidate_url:
            attempt.availability_state = "unavailable"
            attempt.errors.append("No search candidates resolved")
            return

        attempt.requested_urls.append(candidate_url)
        sha = hashlib.sha256(f"{org}|{candidate_url}|{candidate_title}".encode()).hexdigest()
        attempt.raw_snapshot_hashes.append(sha)

        # Entity reverse proof check
        clean_name = re.sub(r"[^a-zA-Z0-9æøåÆØÅ]", "", name.lower())
        clean_title = re.sub(r"[^a-zA-Z0-9æøåÆØÅ]", "", candidate_title.lower())
        name_match = (clean_name[:8] in clean_title) or (clean_title[:8] in clean_name)

        if name_match:
            attempt.exact_identity_evidence.append({
                "type": f"{evidence_source}_title_match",
                "matched_title": candidate_title,
                "company_name": name,
            })
            attempt.record_claim(Claim(
                field="candidate_web_presence",
                value={"url": candidate_url, "title": candidate_title, "source": evidence_source},
                confidence=0.91,
                evidence_span=f"Search candidate discovered for {name}: {candidate_title} ({candidate_url})",
                content_hash=sha,
                source_url=candidate_url,
                status="accepted",
            ))
        else:
            attempt.record_claim(Claim(
                field="candidate_web_presence",
                value={"url": candidate_url, "title": candidate_title},
                confidence=0.25,
                evidence_span=f"Search result {candidate_title} failed title match with {name}",
                content_hash=sha,
                source_url=candidate_url,
                status="rejected",
                rejection_reason="failed_title_reverse_identity_gate",
            ))
            attempt.availability_state = "partial"
