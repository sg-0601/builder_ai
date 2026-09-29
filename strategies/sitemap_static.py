"""Sitemap and robots discovery strategy (sitemap_static_v1)."""

from __future__ import annotations

import hashlib
import re
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from typing import Any

from strategies.base import BaseStrategy, Claim, StrategyAttempt

UA_HEADER = "SignalpostResearch/1.0 (+https://builderr.ai; Norwegian company research agent)"
PRIORITY_KEYWORDS = ("om-oss", "about", "kontakt", "contact", "ledelse", "team", "karriere", "careers", "nyheter")


class SitemapStaticStrategy(BaseStrategy):
    name = "sitemap_static"
    version = "1.0.0"

    def _run(self, company: dict[str, Any], attempt: StrategyAttempt, **kwargs: Any) -> None:
        org = str(company.get("organisation_number") or "")
        name = str(company.get("name") or "")
        raw_website = str(company.get("website") or "").strip()

        if not raw_website:
            attempt.availability_state = "unavailable"
            attempt.errors.append("No base website available for sitemap probe")
            return

        if not re.match(r"^https?://", raw_website, re.I):
            base_url = "https://" + raw_website
        else:
            base_url = raw_website

        parsed = urllib.parse.urlparse(base_url)
        sitemap_candidates = [
            f"{parsed.scheme}://{parsed.netloc}/sitemap.xml",
            f"{parsed.scheme}://{parsed.netloc}/sitemap_index.xml",
        ]

        found_urls: list[str] = []
        for s_url in sitemap_candidates:
            attempt.requested_urls.append(s_url)
            attempt.request_count += 1
            try:
                req = urllib.request.Request(s_url, headers={"User-Agent": UA_HEADER})
                with urllib.request.urlopen(req, timeout=4.0) as resp:
                    if resp.status == 200:
                        content = resp.read(500_000)
                        sha = hashlib.sha256(content).hexdigest()
                        attempt.raw_snapshot_hashes.append(sha)
                        root = ET.fromstring(content)
                        for loc in root.findall(".//{*}loc"):
                            if loc.text:
                                found_urls.append(loc.text.strip())
                        break
            except Exception:
                continue

        if not found_urls:
            attempt.availability_state = "unavailable"
            attempt.errors.append("No readable XML sitemap discovered")
            return

        # Filter priority URLs
        priority_pages: list[str] = []
        for u in found_urls:
            u_lower = u.lower()
            if any(term in u_lower for term in PRIORITY_KEYWORDS):
                priority_pages.append(u)

        priority_pages = priority_pages[:5]  # Bounded to top 5
        attempt.record_claim(Claim(
            field="sitemap_discovered_pages",
            value=priority_pages,
            confidence=0.92,
            evidence_span=f"Discovered {len(priority_pages)} priority structural pages via sitemap for {name}",
            content_hash=attempt.raw_snapshot_hashes[-1] if attempt.raw_snapshot_hashes else "none",
            source_url=s_url,
            status="accepted" if priority_pages else "rejected",
            rejection_reason=None if priority_pages else "no_priority_pages_in_sitemap",
        ))
