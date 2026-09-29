"""Targeted subpath crawling for leadership, contact, and locations (targeted_paths_v1)."""

from __future__ import annotations

import hashlib
import re
import urllib.parse
import urllib.request
from typing import Any
from bs4 import BeautifulSoup

from strategies.base import BaseStrategy, Claim, StrategyAttempt

UA_HEADER = "SignalpostResearch/1.0 (+https://builderr.ai; Norwegian company research agent)"
PATHS_TO_PROBE = ["/om-oss", "/about", "/kontakt", "/contact", "/ledelse"]


class TargetedPathsStrategy(BaseStrategy):
    name = "targeted_paths"
    version = "1.0.0"

    def _run(self, company: dict[str, Any], attempt: StrategyAttempt, **kwargs: Any) -> None:
        org = str(company.get("organisation_number") or "")
        name = str(company.get("name") or "")
        raw_website = str(company.get("website") or "").strip()

        if not raw_website:
            attempt.availability_state = "unavailable"
            attempt.errors.append("No base website for targeted path probe")
            return

        if not re.match(r"^https?://", raw_website, re.I):
            base_url = "https://" + raw_website
        else:
            base_url = raw_website

        parsed = urllib.parse.urlparse(base_url)
        extracted_phones: set[str] = set()
        extracted_emails: set[str] = set()

        for path in PATHS_TO_PROBE[:3]:  # strict request boundedness
            target_url = f"{parsed.scheme}://{parsed.netloc}{path}"
            attempt.requested_urls.append(target_url)
            attempt.request_count += 1
            try:
                req = urllib.request.Request(target_url, headers={"User-Agent": UA_HEADER})
                with urllib.request.urlopen(req, timeout=4.0) as resp:
                    if resp.status == 200:
                        content = resp.read(300_000)
                        sha = hashlib.sha256(content).hexdigest()
                        attempt.raw_snapshot_hashes.append(sha)
                        text = content.decode("utf-8", errors="replace")

                        # Phone regex (Norwegian 8-digit or +47)
                        phones = re.findall(r"(?:(?:\+47|0047)\s*)?[2-9]\d{1}(?:\s*\d{2}){3}", text)
                        for p in phones:
                            clean_p = re.sub(r"\s+", "", p)
                            if len(clean_p) >= 8:
                                extracted_phones.add(clean_p)

                        # Email regex
                        emails = re.findall(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}", text)
                        for em in emails:
                            if not em.endswith(".png") and not em.endswith(".jpg"):
                                extracted_emails.add(em.lower())
            except Exception:
                continue

        if extracted_phones or extracted_emails:
            attempt.record_claim(Claim(
                field="contact_channels",
                value={"phones": list(extracted_phones)[:2], "emails": list(extracted_emails)[:2]},
                confidence=0.90,
                evidence_span=f"Direct contact channels extracted from targeted pages of {name}",
                content_hash=attempt.raw_snapshot_hashes[-1] if attempt.raw_snapshot_hashes else "none",
                source_url=base_url,
                status="accepted",
            ))
        else:
            attempt.availability_state = "partial"
            attempt.record_claim(Claim(
                field="contact_channels",
                value=None,
                confidence=0.30,
                evidence_span="No phone or email patterns matched in probed subpaths",
                content_hash="none",
                source_url=base_url,
                status="rejected",
                rejection_reason="no_contact_patterns_matched",
            ))
