"""Annual accounts PDF fallback strategy (pdf_fallback_v1)."""

from __future__ import annotations

import hashlib
import json
import urllib.parse
import urllib.request
from typing import Any

from strategies.base import BaseStrategy, Claim, StrategyAttempt

UA_HEADER = "SignalpostResearch/1.0 (+https://builderr.ai; Norwegian company research agent)"


class PdfFallbackStrategy(BaseStrategy):
    name = "pdf_fallback"
    version = "1.0.0"

    def _run(self, company: dict[str, Any], attempt: StrategyAttempt, **kwargs: Any) -> None:
        org = str(company.get("organisation_number") or "")
        name = str(company.get("name") or "")
        latest_year = str(company.get("latest_submitted_accounts") or "")

        # Official Brreg Regnskapsregisteret API endpoint
        url = f"https://data.brreg.no/regnskapsregisteret/regnskap/selskap/{org}/aarsregnskap"
        attempt.requested_urls.append(url)
        attempt.request_count += 1

        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA_HEADER, "Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=5.0) as resp:
                data = json.loads(resp.read().decode("utf-8", errors="replace"))

            accounts = data if isinstance(data, list) else data.get("aarsregnskap", [])
            if not accounts:
                attempt.availability_state = "unavailable"
                attempt.errors.append("No official accounts filed in Regnskapsregisteret")
                return

            latest = accounts[0]
            year = str(latest.get("regnskapsperiode", {}).get("tilDato", "")[:4] or latest_year)
            currency = str(latest.get("valuta") or "NOK")
            rev = latest.get("egenkapitalGjeld", {}).get("sumEgenkapitalGjeld") or latest.get("eiendeler", {}).get("sumEiendeler")

            sha = hashlib.sha256(json.dumps(latest, sort_keys=True).encode()).hexdigest()
            attempt.raw_snapshot_hashes.append(sha)

            attempt.record_claim(Claim(
                field="annual_accounts_filing",
                value={"year": year, "currency": currency, "total_balance": rev},
                confidence=0.99,
                evidence_span=f"Official annual accounts filed for {name} ({org}) for fiscal year {year}",
                content_hash=sha,
                source_url=url,
                status="accepted",
            ))
        except Exception as e:
            attempt.availability_state = "failed"
            attempt.errors.append(f"Regnskapsregisteret API query failed: {str(e)[:150]}")
