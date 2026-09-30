"""JSON-LD and OpenGraph metadata extraction strategy (jsonld_opengraph_v1).

Extracts structured semantic data (JSON-LD schema.org Organization, LocalBusiness,
sameAs social profiles, legal names) and OpenGraph tags from the company homepage
using extruct and BeautifulSoup.
"""

from __future__ import annotations

import hashlib
import json
import re
import urllib.parse
import urllib.request
from typing import Any

from bs4 import BeautifulSoup
import extruct

from strategies.base import BaseStrategy, Claim, StrategyAttempt

UA_HEADER = "SignalpostResearch/1.0 (+https://builderr.ai; Norwegian company research agent)"


class JsonLdOpenGraphStrategy(BaseStrategy):
    """Strategy: JSON-LD and OpenGraph extraction (v1.0.0)."""
    name = "jsonld_opengraph"
    version = "1.0.0"

    def _run(self, company: dict[str, Any], attempt: StrategyAttempt, **kwargs: Any) -> None:
        org = str(company.get("organisation_number") or "")
        name = str(company.get("name") or "")
        raw_website = str(company.get("website") or "").strip()

        if not raw_website:
            attempt.availability_state = "unavailable"
            attempt.errors.append("No website declared for structured data extraction")
            return

        if not re.match(r"^https?://", raw_website, re.I):
            target_url = "https://" + raw_website
        else:
            target_url = raw_website

        parsed = urllib.parse.urlparse(target_url)
        if not parsed.hostname:
            attempt.availability_state = "failed"
            attempt.errors.append(f"Invalid URL structure: {raw_website}")
            return

        attempt.requested_urls.append(target_url)
        attempt.candidate_domains.append(parsed.hostname.lower())
        attempt.request_count += 1

        try:
            req = urllib.request.Request(
                target_url,
                headers={"User-Agent": UA_HEADER, "Accept": "text/html,application/xhtml+xml"},
            )
            with urllib.request.urlopen(req, timeout=5.0) as resp:
                final_url = resp.geturl()
                raw_bytes = resp.read(2_000_000)
        except Exception as exc:
            attempt.availability_state = "failed"
            attempt.errors.append(f"HTTP fetch failed for structured data: {str(exc)[:150]}")
            return

        sha256_hash = hashlib.sha256(raw_bytes).hexdigest()
        attempt.raw_snapshot_hashes.append(sha256_hash)
        attempt.redirect_chain.append(final_url)

        html_text = raw_bytes.decode("utf-8", errors="replace")

        # 1. OpenGraph extraction via BeautifulSoup
        soup = BeautifulSoup(html_text, "html.parser")
        og_data: dict[str, str] = {}
        for prop in ["title", "description", "image", "url", "site_name", "type"]:
            tag = soup.select_one(f'meta[property="og:{prop}"], meta[name="og:{prop}"]')
            if tag and tag.get("content"):
                og_data[prop] = str(tag.get("content")).strip()

        # 2. Extruct extraction (JSON-LD, microdata, opengraph)
        structured_orgs: list[dict[str, Any]] = []
        same_as_links: list[str] = []
        try:
            extracted = extruct.extract(html_text, base_url=final_url, syntaxes=["json-ld", "opengraph"])
            json_ld_items = extracted.get("json-ld", [])

            def find_orgs(item: Any):
                if isinstance(item, dict):
                    kind = item.get("@type", "")
                    kinds = [kind] if isinstance(kind, str) else list(kind) if isinstance(kind, list) else []
                    if any(k in ["Organization", "Corporation", "LocalBusiness", "LegalEntity"] for k in kinds):
                        org_dict = {
                            "type": kinds,
                            "name": item.get("name"),
                            "legal_name": item.get("legalName"),
                            "url": item.get("url"),
                            "telephone": item.get("telephone"),
                            "email": item.get("email"),
                            "address": item.get("address"),
                        }
                        structured_orgs.append({k: v for k, v in org_dict.items() if v is not None})
                    # Harvest sameAs links
                    same_as = item.get("sameAs", [])
                    if isinstance(same_as, str):
                        same_as_links.append(same_as)
                    elif isinstance(same_as, list):
                        same_as_links.extend(str(s) for s in same_as if isinstance(s, str))

                    for v in item.values():
                        find_orgs(v)
                elif isinstance(item, list):
                    for sub in item:
                        find_orgs(sub)

            find_orgs(json_ld_items)
        except Exception as e:
            attempt.errors.append(f"extruct parsing error: {str(e)[:100]}")

        has_data = bool(og_data or structured_orgs or same_as_links)

        if structured_orgs:
            attempt.record_claim(Claim(
                field="jsonld_organizations",
                value=structured_orgs[:3],
                confidence=0.98,
                evidence_span=f"Extracted {len(structured_orgs)} schema.org Organization entities for {name}",
                content_hash=sha256_hash,
                source_url=final_url,
                status="accepted",
            ))

        if same_as_links:
            attempt.record_claim(Claim(
                field="structured_social_links",
                value=list(set(same_as_links))[:5],
                confidence=0.95,
                evidence_span=f"JSON-LD sameAs profiles: {', '.join(list(set(same_as_links))[:3])}",
                content_hash=sha256_hash,
                source_url=final_url,
                status="accepted",
            ))

        if og_data:
            og_summary = f"og:title='{og_data.get('title', '')[:80]}', og:desc='{og_data.get('description', '')[:100]}'"
            attempt.record_claim(Claim(
                field="opengraph_metadata",
                value=og_data,
                confidence=0.96,
                evidence_span=f"OpenGraph tags on {final_url}: {og_summary}",
                content_hash=sha256_hash,
                source_url=final_url,
                status="accepted",
            ))

        if has_data:
            attempt.availability_state = "success"
        else:
            attempt.availability_state = "unavailable"
            attempt.errors.append("No JSON-LD or OpenGraph tags found in HTML")
            attempt.record_claim(Claim(
                field="jsonld_opengraph_status",
                value={"status": "not_found"},
                confidence=0.80,
                evidence_span="No JSON-LD or OpenGraph semantic metadata detected on homepage",
                content_hash=sha256_hash,
                source_url=final_url,
                status="rejected",
                rejection_reason="no_structured_data_tags_found",
            ))
