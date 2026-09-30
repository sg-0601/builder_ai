"""Registry-provided website discovery and extraction strategy (registry_site_v1)."""

from __future__ import annotations

import hashlib
import json
import re
import ssl
import urllib.parse
import urllib.request
import urllib.robotparser
from typing import Any
from bs4 import BeautifulSoup

from strategies.base import BaseStrategy, Claim, StrategyAttempt

UA_HEADER = "SignalpostResearch/1.0 (+https://builderr.ai; Norwegian company research agent)"


class RegistrySiteStrategy(BaseStrategy):
    name = "registry_site"
    version = "1.0.0"

    def _run(self, company: dict[str, Any], attempt: StrategyAttempt, **kwargs: Any) -> None:
        org = str(company.get("organisation_number") or "")
        name = str(company.get("name") or "")
        raw_website = str(company.get("website") or "").strip()

        if not raw_website:
            attempt.availability_state = "unavailable"
            attempt.errors.append("No website declared in official registry profile")
            return

        # URL Normalization
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

        # Check robots.txt
        robots_url = f"{parsed.scheme}://{parsed.netloc}/robots.txt"
        rp = urllib.robotparser.RobotFileParser()
        rp.set_url(robots_url)
        attempt.request_count += 1
        try:
            req_rob = urllib.request.Request(robots_url, headers={"User-Agent": UA_HEADER})
            with urllib.request.urlopen(req_rob, timeout=3.0) as r_resp:
                rp.parse(r_resp.read().decode("utf-8", errors="replace").splitlines())
            allowed = rp.can_fetch(UA_HEADER, target_url)
        except Exception:
            allowed = True

        if not allowed:
            attempt.availability_state = "unavailable"
            attempt.errors.append(f"Disallowed by robots.txt: {target_url}")
            return

        # Fetch homepage
        attempt.request_count += 1
        ssl_ctx = ssl._create_unverified_context()
        try:
            req = urllib.request.Request(target_url, headers={"User-Agent": UA_HEADER, "Accept": "text/html"})
            with urllib.request.urlopen(req, timeout=5.0, context=ssl_ctx) as resp:
                final_url = resp.geturl()
                raw_bytes = resp.read(1_000_000)
                status_code = resp.status
        except Exception as e:
            attempt.availability_state = "failed"
            attempt.errors.append(f"HTTP Fetch Failed: {str(e)[:150]}")
            return

        attempt.redirect_chain.append(final_url)
        sha256_hash = hashlib.sha256(raw_bytes).hexdigest()
        attempt.raw_snapshot_hashes.append(sha256_hash)

        # Parse HTML & Metadata
        html_text = raw_bytes.decode("utf-8", errors="replace")
        soup = BeautifulSoup(html_text, "html.parser")
        page_title = soup.title.get_text(strip=True) if soup.title else ""

        # Preserve snapshot data on attempt for zero-cost in-memory reuse by downstream strategies
        setattr(attempt, "raw_bytes", raw_bytes)
        setattr(attempt, "html_text", html_text)
        setattr(attempt, "final_url", final_url)

        # Identity Verification: Does company name, brand token, or org number appear?
        clean_name = re.sub(r"[^a-zA-Z0-9æøåÆØÅ]", "", name.lower())
        body_text = soup.get_text(" ", strip=True).lower()
        clean_body = re.sub(r"[^a-zA-Z0-9æøåÆØÅ]", "", body_text)
        
        # Token-based brand matching for legal name variations (e.g., WYSSEN NORGE AS -> wyssen)
        stop_tokens = {"as", "asa", "ans", "da", "ks", "norge", "norway", "group", "holding", "drift", "eiendom"}
        distinctive_tokens = [t for t in re.findall(r"[a-z0-9æøå]+", name.lower()) if t not in stop_tokens and len(t) >= 3]
        brand_match = bool(distinctive_tokens and all(
            t in body_text or t in page_title.lower() or t in parsed.hostname.lower()
            for t in distinctive_tokens
        ))

        has_identity_match = (org in body_text) or (clean_name and clean_name[:12] in clean_body) or brand_match

        if has_identity_match:
            attempt.exact_identity_evidence.append({
                "type": "exact_name_or_org_found_in_page",
                "org": org,
                "domain": parsed.hostname,
            })

            # Record Accepted Website Claim
            attempt.record_claim(Claim(
                field="website",
                value=final_url,
                confidence=0.98,
                evidence_span=f"Verified registry website matching {name}: {final_url}",
                content_hash=sha256_hash,
                source_url=final_url,
                status="accepted",
            ))

            # Record Accepted Title/Description Claim
            if page_title:
                attempt.record_claim(Claim(
                    field="website_title",
                    value=page_title,
                    confidence=0.95,
                    evidence_span=f"Page title for {name}: {page_title}",
                    content_hash=sha256_hash,
                    source_url=final_url,
                    status="accepted",
                ))
        else:
            # Rejection due to identity failure
            attempt.record_claim(Claim(
                field="website",
                value=final_url,
                confidence=0.30,
                evidence_span=f"Page {final_url} did not contain orgnr {org} or name match for {name}",
                content_hash=sha256_hash,
                source_url=final_url,
                status="rejected",
                rejection_reason="failed_reverse_identity_gate",
            ))
            attempt.availability_state = "partial"
