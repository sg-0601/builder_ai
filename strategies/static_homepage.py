"""Static homepage crawl strategy (static_homepage_crawl_v1).

Extracts clean readable text, page title, meta description, and structural
features from the static HTML of a company's official homepage using Trafilatura
and BeautifulSoup.
"""

from __future__ import annotations

import hashlib
import json
import re
import urllib.parse
import urllib.request
from typing import Any

from bs4 import BeautifulSoup
import trafilatura

from strategies.base import BaseStrategy, Claim, StrategyAttempt

UA_HEADER = "SignalpostResearch/1.0 (+https://builderr.ai; Norwegian company research agent)"


class StaticHomepageStrategy(BaseStrategy):
    """Strategy: Static homepage crawl (v1.0.0).
    
    Performs deterministic static HTML fetching, clean readability extraction
    via Trafilatura, and metadata extraction.
    """
    name = "static_homepage_crawl"
    version = "1.0.0"

    def _run(self, company: dict[str, Any], attempt: StrategyAttempt, **kwargs: Any) -> None:
        org = str(company.get("organisation_number") or "")
        name = str(company.get("name") or "")
        raw_website = str(company.get("website") or "").strip()

        if not raw_website:
            attempt.availability_state = "unavailable"
            attempt.errors.append("No website URL declared for static homepage crawl")
            return

        if not re.match(r"^https?://", raw_website, re.I):
            target_url = "https://" + raw_website
        else:
            target_url = raw_website

        parsed = urllib.parse.urlparse(target_url)
        if not parsed.hostname:
            attempt.availability_state = "failed"
            attempt.errors.append(f"Invalid website URL: {raw_website}")
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
                content = resp.read(2_000_000)
                status_code = resp.status
        except Exception as exc:
            attempt.availability_state = "failed"
            attempt.errors.append(f"Static homepage fetch failed: {str(exc)[:150]}")
            return

        attempt.redirect_chain.append(final_url)
        sha256_hash = hashlib.sha256(content).hexdigest()
        attempt.raw_snapshot_hashes.append(sha256_hash)

        html_text = content.decode("utf-8", errors="replace")
        soup = BeautifulSoup(html_text, "html.parser")

        # 1. Page title
        title = soup.title.get_text(" ", strip=True)[:300] if soup.title else ""

        # 2. Meta description
        meta_tag = soup.select_one('meta[name="description"], meta[property="og:description"]')
        meta_desc = str(meta_tag.get("content") or "").strip()[:500] if meta_tag else ""

        # 3. Clean readable text via Trafilatura
        clean_text = trafilatura.extract(
            html_text,
            url=final_url,
            include_links=False,
            include_tables=False,
            favor_precision=True,
        ) or ""

        words = clean_text.split()
        word_count = len(words)
        text_excerpt = clean_text[:800] if clean_text else ""

        # Reverse identity verification
        clean_name = re.sub(r"[^a-zA-Z0-9æøåÆØÅ]", "", name.lower())
        body_text = soup.get_text(" ", strip=True).lower()
        clean_body = re.sub(r"[^a-zA-Z0-9æøåÆØÅ]", "", body_text)
        name_matched = bool(clean_name and clean_name[:12] in clean_body)
        org_matched = bool(org and org in body_text)

        if name_matched or org_matched:
            attempt.exact_identity_evidence.append({
                "type": "exact_name_or_org_found_in_homepage",
                "org_number": org,
                "domain": parsed.hostname,
                "name_found": name_matched,
                "org_found": org_matched,
            })

            # Record homepage content claim
            evidence_str = f"Homepage of {name}: title='{title[:80]}', words={word_count}"
            if meta_desc:
                evidence_str += f", desc='{meta_desc[:120]}'"

            attempt.record_claim(Claim(
                field="homepage_content",
                value={
                    "url": final_url,
                    "title": title,
                    "meta_description": meta_desc,
                    "word_count": word_count,
                    "text_excerpt": text_excerpt[:400],
                },
                confidence=0.98,
                evidence_span=evidence_str,
                content_hash=sha256_hash,
                source_url=final_url,
                status="accepted",
            ))

            if meta_desc:
                attempt.record_claim(Claim(
                    field="meta_description",
                    value=meta_desc,
                    confidence=0.95,
                    evidence_span=meta_desc,
                    content_hash=sha256_hash,
                    source_url=final_url,
                    status="accepted",
                ))

            attempt.availability_state = "success"
        else:
            attempt.record_claim(Claim(
                field="homepage_content",
                value={"url": final_url, "title": title},
                confidence=0.35,
                evidence_span=f"Page {final_url} did not contain company name {name} or orgnr {org}",
                content_hash=sha256_hash,
                source_url=final_url,
                status="rejected",
                rejection_reason="failed_reverse_identity_gate",
            ))
            attempt.availability_state = "partial"
