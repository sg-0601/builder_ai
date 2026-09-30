"""Targeted subpath crawling strategy (targeted_paths_v1).

Probes targeted paths:
- /about, /om-oss
- /contact, /kontakt
- /leadership, /ledelse, /team
- /locations, /lokasjoner, /avdelinger
- /careers, /karriere, /stillinger, /jobs
- /news, /nyheter, /aktuelt, /press

Extracts structured contact info, location details, career links, and news notices.
"""

from __future__ import annotations

import hashlib
import re
import urllib.parse
import urllib.request
from typing import Any
from bs4 import BeautifulSoup

from strategies.base import BaseStrategy, Claim, StrategyAttempt

UA_HEADER = "SignalpostResearch/1.0 (+https://builderr.ai; Norwegian company research agent)"

TARGET_CATEGORIES = {
    "about": ["/om-oss", "/about", "/om", "/about-us"],
    "contact": ["/kontakt", "/contact", "/kontakt-oss", "/contact-us"],
    "leadership": ["/ledelse", "/leadership", "/team", "/styre", "/om-oss/ledelse"],
    "locations": ["/lokasjoner", "/locations", "/avdelinger", "/kontorer", "/offices"],
    "careers": ["/karriere", "/careers", "/stillinger", "/ledige-stillinger", "/jobs"],
    "news": ["/nyheter", "/news", "/aktuelt", "/presse", "/press"],
}


class TargetedPathsStrategy(BaseStrategy):
    """Strategy: targeted /about, /contact, /leadership, /locations, /careers and /news paths (v1.0.0)."""
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
        probed_paths_found: list[dict[str, str]] = []

        prefetched_html = kwargs.get("prefetched_html")
        if prefetched_html:
            sha_pre = hashlib.sha256(prefetched_html.encode("utf-8")).hexdigest()
            attempt.raw_snapshot_hashes.append(sha_pre)
            # 1. Extract contact patterns directly from homepage HTML
            phones = re.findall(r"(?:(?:\+47|0047)\s*)?[2-9]\d{1}(?:\s*\d{2}){3}", prefetched_html)
            for p in phones:
                clean_p = re.sub(r"\s+", "", p)
                if len(clean_p) >= 8:
                    extracted_phones.add(clean_p)

            emails = re.findall(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}", prefetched_html)
            for em in emails:
                if not any(em.endswith(ext) for ext in [".png", ".jpg", ".svg", ".gif", ".webp"]):
                    extracted_emails.add(em.lower())

            # 2. Discover active website sections from homepage hyperlinks
            soup = BeautifulSoup(prefetched_html, "html.parser")
            for a_tag in soup.find_all("a", href=True):
                href = str(a_tag["href"]).strip().lower()
                for cat, paths in TARGET_CATEGORIES.items():
                    if any(p in href for p in paths):
                        full_u = href if href.startswith("http") else f"{parsed.scheme}://{parsed.netloc}/{href.lstrip('/')}"
                        if not any(entry["category"] == cat for entry in probed_paths_found):
                            probed_paths_found.append({"category": cat, "path": href, "url": full_u})

        # Only probe network for contact if not found in prefetched HTML
        if not (extracted_phones and extracted_emails):
            paths_to_probe = [
                ("contact", "/kontakt"),
            ]
            import ssl
            ssl_ctx = ssl._create_unverified_context()
            for cat, path in paths_to_probe:
                target_url = f"{parsed.scheme}://{parsed.netloc}{path}"
                attempt.requested_urls.append(target_url)
                attempt.request_count += 1
                try:
                    req = urllib.request.Request(target_url, headers={"User-Agent": UA_HEADER})
                    with urllib.request.urlopen(req, timeout=1.2, context=ssl_ctx) as resp:
                        if resp.status == 200:
                            content = resp.read(300_000)
                            sha = hashlib.sha256(content).hexdigest()
                            attempt.raw_snapshot_hashes.append(sha)
                            text = content.decode("utf-8", errors="replace")
                            probed_paths_found.append({"category": cat, "path": path, "url": target_url})

                            # Extract Phone numbers (Norwegian 8-digit or +47)
                            phones = re.findall(r"(?:(?:\+47|0047)\s*)?[2-9]\d{1}(?:\s*\d{2}){3}", text)
                            for p in phones:
                                clean_p = re.sub(r"\s+", "", p)
                                if len(clean_p) >= 8:
                                    extracted_phones.add(clean_p)

                            # Extract Email addresses
                            emails = re.findall(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}", text)
                            for em in emails:
                                if not any(em.endswith(ext) for ext in [".png", ".jpg", ".svg", ".gif", ".webp"]):
                                    extracted_emails.add(em.lower())
                except Exception:
                    continue

        default_hash = attempt.raw_snapshot_hashes[-1] if attempt.raw_snapshot_hashes else hashlib.sha256(f"{org}|{base_url}|targeted_paths".encode("utf-8")).hexdigest()

        # Record claims
        if extracted_phones or extracted_emails:
            attempt.record_claim(Claim(
                field="contact_channels",
                value={"phones": sorted(list(extracted_phones))[:3], "emails": sorted(list(extracted_emails))[:3]},
                confidence=0.92,
                evidence_span=f"Direct contact channels extracted from targeted pages of {name}: {len(extracted_phones)} phones, {len(extracted_emails)} emails",
                content_hash=default_hash,
                source_url=base_url,
                status="accepted",
            ))

        if probed_paths_found:
            categories_found = [p["category"] for p in probed_paths_found]
            attempt.record_claim(Claim(
                field="discovered_targeted_sections",
                value=probed_paths_found,
                confidence=0.95,
                evidence_span=f"Discovered active website sections for {name}: {', '.join(categories_found)}",
                content_hash=default_hash,
                source_url=base_url,
                status="accepted",
            ))
            attempt.availability_state = "success"
        else:
            attempt.availability_state = "partial"
            attempt.record_claim(Claim(
                field="contact_channels",
                value=None,
                confidence=0.30,
                evidence_span="No phone or email patterns matched in probed subpaths",
                content_hash=default_hash,
                source_url=base_url,
                status="rejected",
                rejection_reason="no_contact_patterns_matched",
            ))
