"""Leader and founder bridge strategy (leader_founder_bridge_v1).

Bridges official statutory roles from Brønnøysund Register Centre
(daglig leder / CEO, styreleder / chair, board members) to the public
commercial brand by verifying their presence on the company's public website.
"""

from __future__ import annotations

import hashlib
import json
import re
import urllib.parse
import urllib.request
from typing import Any

from bs4 import BeautifulSoup

from strategies.base import BaseStrategy, Claim, StrategyAttempt

UA_HEADER = "SignalpostResearch/1.0 (+https://builderr.ai; Norwegian company research agent)"


def fetch_official_roles_brreg(org: str) -> list[dict[str, str]]:
    """Fetch official registered roles from Brreg public API."""
    url = f"https://data.brreg.no/enhetsregisteret/api/enheter/{org}/roller"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": UA_HEADER, "Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=4.0) as resp:
            data = json.loads(resp.read().decode("utf-8", errors="replace"))
        roles: list[dict[str, str]] = []
        for group in data.get("rollegrupper", []):
            for r in group.get("roller", []):
                person = r.get("person", {})
                name_parts = person.get("navn", {})
                first = name_parts.get("fornavn", "")
                middle = name_parts.get("mellomnavn", "")
                last = name_parts.get("etternavn", "")
                full_name = " ".join(filter(None, [first, middle, last]))
                role_type = r.get("type", {}).get("beskrivelse") or r.get("type", {}).get("kode") or "Styremedlem"
                if full_name:
                    roles.append({"name": full_name, "role": role_type})
        return roles
    except Exception:
        return []


class LeaderFounderBridgeStrategy(BaseStrategy):
    """Strategy: leader/founder bridge from official role to public brand (v1.0.0)."""
    name = "leader_founder_bridge"
    version = "1.0.0"

    def _run(self, company: dict[str, Any], attempt: StrategyAttempt, **kwargs: Any) -> None:
        org = str(company.get("organisation_number") or "")
        company_name = str(company.get("name") or "")
        raw_website = str(company.get("website") or "").strip()

        # 1. Obtain official roles
        official_roles: list[dict[str, str]] = []
        # Check if already present in company dictionary
        if "roles" in company and isinstance(company["roles"], list):
            official_roles = company["roles"]
        else:
            official_roles = fetch_official_roles_brreg(org)
            attempt.request_count += 1

        if not official_roles:
            attempt.availability_state = "unavailable"
            attempt.errors.append(f"No official registered roles found for orgnr {org}")
            return

        if not raw_website:
            attempt.availability_state = "unavailable"
            attempt.errors.append("No website available to bridge leadership against")
            return

        if not re.match(r"^https?://", raw_website, re.I):
            base_url = "https://" + raw_website
        else:
            base_url = raw_website

        parsed = urllib.parse.urlparse(base_url)
        bridged_leaders: list[dict[str, Any]] = []

        prefetched_html = kwargs.get("prefetched_html")
        if prefetched_html:
            text_lower = prefetched_html.casefold()
            sha = hashlib.sha256(prefetched_html.encode("utf-8")).hexdigest()
            attempt.raw_snapshot_hashes.append(sha)
            for role_info in official_roles:
                person_name = role_info["name"]
                name_tokens = [t.casefold() for t in person_name.split() if len(t) > 2]
                if len(name_tokens) >= 2:
                    if person_name.casefold() in text_lower or f"{name_tokens[0]} {name_tokens[-1]}" in text_lower:
                        bridged_leaders.append({
                            "name": person_name,
                            "official_role": role_info["role"],
                            "source_url": base_url,
                            "evidence_span": f"Official {role_info['role']} '{person_name}' verified on public site {base_url}",
                            "content_hash": sha,
                        })

        if not bridged_leaders:
            pages_to_check = [
                f"{parsed.scheme}://{parsed.netloc}/om-oss",
            ]
            import ssl
            ssl_ctx = ssl._create_unverified_context()
            for p_url in pages_to_check:
                attempt.requested_urls.append(p_url)
                attempt.request_count += 1
                try:
                    req = urllib.request.Request(p_url, headers={"User-Agent": UA_HEADER, "Accept": "text/html"})
                    with urllib.request.urlopen(req, timeout=1.2, context=ssl_ctx) as resp:
                        if resp.status == 200:
                            content = resp.read(500_000)
                            sha = hashlib.sha256(content).hexdigest()
                            attempt.raw_snapshot_hashes.append(sha)
                            html_text = content.decode("utf-8", errors="replace")
                            text_lower = html_text.casefold()

                            for role_info in official_roles:
                                person_name = role_info["name"]
                                name_tokens = [t.casefold() for t in person_name.split() if len(t) > 2]
                                if len(name_tokens) >= 2:
                                    # Check if full name or first+last appear together
                                    if person_name.casefold() in text_lower or f"{name_tokens[0]} {name_tokens[-1]}" in text_lower:
                                        bridged_leaders.append({
                                            "name": person_name,
                                            "official_role": role_info["role"],
                                            "source_url": p_url,
                                            "evidence_span": f"Official {role_info['role']} '{person_name}' verified on public site {p_url}",
                                            "content_hash": sha,
                                        })
                            if bridged_leaders:
                                break
                except Exception:
                    continue

        if bridged_leaders:
            attempt.availability_state = "success"
            for bl in bridged_leaders[:3]:
                attempt.record_claim(Claim(
                    field="leader_brand_bridge",
                    value={
                        "leader_name": bl["name"],
                        "official_role": bl["official_role"],
                        "verified_on_public_web": True,
                    },
                    confidence=0.97,
                    evidence_span=bl["evidence_span"],
                    content_hash=bl["content_hash"],
                    source_url=bl["source_url"],
                    status="accepted",
                ))
        else:
            attempt.availability_state = "partial"
            attempt.record_claim(Claim(
                field="leader_brand_bridge",
                value={"verified_count": 0},
                confidence=0.40,
                evidence_span=f"Official role holders for {company_name} not found in public website text excerpts",
                content_hash=attempt.raw_snapshot_hashes[-1] if attempt.raw_snapshot_hashes else hashlib.sha256(f"{org}|{base_url}|roles".encode("utf-8")).hexdigest(),
                source_url=base_url,
                status="rejected",
                rejection_reason="no_leader_names_found_on_public_site",
            ))
