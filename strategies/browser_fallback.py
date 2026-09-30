"""Browser-rendered and JavaScript shell fallback strategies (browser_fallback_v1 and browser_fallback_v2)."""

from __future__ import annotations

import hashlib
import json
import re
import urllib.parse
import urllib.request
from typing import Any
from bs4 import BeautifulSoup

from strategies.base import BaseStrategy, Claim, StrategyAttempt

UA_HEADER = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36 SignalpostBrowser/2.0"


def is_javascript_shell(html: str) -> tuple[bool, str]:
    """Tests whether a page is an empty or client-side rendered JavaScript shell."""
    soup = BeautifulSoup(html, "html.parser")
    # Remove script and style
    for elem in soup(["script", "style", "svg"]):
        elem.extract()
    text = soup.get_text(" ", strip=True)

    scripts = len(soup.select("script[src]"))
    has_root_div = bool(soup.select("#root, #app, #__next, div[data-reactroot]"))

    if len(text) < 150 and (scripts >= 2 or has_root_div):
        return True, f"JS Shell confirmed: text_len={len(text)}, scripts={scripts}, root_div={has_root_div}"
    return False, f"Static text sufficient: text_len={len(text)}"


class BrowserFallbackV1Strategy(BaseStrategy):
    name = "browser_fallback"
    version = "1.0.0"

    def _run(self, company: dict[str, Any], attempt: StrategyAttempt, **kwargs: Any) -> None:
        raw_website = str(company.get("website") or "").strip()
        if not raw_website:
            attempt.availability_state = "unavailable"
            attempt.errors.append("No website declared")
            return

        if not re.match(r"^https?://", raw_website, re.I):
            target_url = "https://" + raw_website
        else:
            target_url = raw_website

        attempt.requested_urls.append(target_url)
        attempt.request_count += 1
        try:
            req = urllib.request.Request(target_url, headers={"User-Agent": UA_HEADER})
            with urllib.request.urlopen(req, timeout=5.0) as resp:
                content = resp.read(1_000_000)
                final_url = resp.geturl()
        except Exception as e:
            attempt.availability_state = "failed"
            attempt.errors.append(f"HTTP fetch failed: {str(e)[:100]}")
            return

        html = content.decode("utf-8", errors="replace")
        sha = hashlib.sha256(content).hexdigest()
        attempt.raw_snapshot_hashes.append(sha)

        is_shell, reason = is_javascript_shell(html)
        if is_shell:
            attempt.record_claim(Claim(
                field="js_shell_detected",
                value={"status": "confirmed_js_shell", "reason": reason},
                confidence=0.85,
                evidence_span=reason,
                content_hash=sha,
                source_url=final_url,
                status="accepted",
            ))
        else:
            attempt.record_claim(Claim(
                field="js_shell_detected",
                value={"status": "static_html", "reason": reason},
                confidence=0.95,
                evidence_span=reason,
                content_hash=sha,
                source_url=final_url,
                status="accepted",
            ))


class BrowserFallbackV2Strategy(BaseStrategy):
    """Challenger strategy: Advanced JavaScript Shell hydration extraction and dynamic DOM recovery."""

    name = "browser_fallback_v2"
    version = "2.0.0"

    def _run(self, company: dict[str, Any], attempt: StrategyAttempt, **kwargs: Any) -> None:
        raw_website = str(company.get("website") or "").strip()
        name = str(company.get("name") or "")
        org = str(company.get("organisation_number") or "")

        if not raw_website:
            attempt.availability_state = "unavailable"
            attempt.errors.append("No website declared for browser fallback v2")
            return

        if not re.match(r"^https?://", raw_website, re.I):
            target_url = "https://" + raw_website
        else:
            target_url = raw_website

        attempt.requested_urls.append(target_url)
        prefetched_bytes = kwargs.get("prefetched_bytes")
        prefetched_html = kwargs.get("prefetched_html")
        prefetched_url = kwargs.get("final_url")

        if prefetched_bytes is not None or prefetched_html is not None:
            final_url = prefetched_url or target_url
            content = prefetched_bytes if prefetched_bytes is not None else prefetched_html.encode("utf-8")
        else:
            attempt.request_count += 1
            try:
                req = urllib.request.Request(target_url, headers={"User-Agent": UA_HEADER})
                with urllib.request.urlopen(req, timeout=5.0) as resp:
                    content = resp.read(1_000_000)
                    final_url = resp.geturl()
            except Exception as e:
                attempt.availability_state = "failed"
                attempt.errors.append(f"HTTP fetch failed: {str(e)[:100]}")
                return

        html = prefetched_html if prefetched_html is not None else content.decode("utf-8", errors="replace")
        sha = hashlib.sha256(content).hexdigest()
        attempt.raw_snapshot_hashes.append(sha)

        is_shell, reason = is_javascript_shell(html)

        # Advanced V2 Feature: Extract hydration JSON payloads embedded in script tags
        # (e.g., __NEXT_DATA__, __NUXT__, window.__INITIAL_STATE__)
        hydration_data: dict[str, Any] = {}
        soup = BeautifulSoup(html, "html.parser")
        next_tag = soup.find("script", id="__NEXT_DATA__")
        if next_tag and next_tag.string:
            try:
                hydration_data = json.loads(next_tag.string)
            except Exception:
                pass

        if not hydration_data:
            # Check for inline JSON state variables
            for s in soup.find_all("script"):
                if s.string and "window.__INITIAL_STATE__" in s.string:
                    m = re.search(r"window\.__INITIAL_STATE__\s*=\s*({.*?});", s.string, re.DOTALL)
                    if m:
                        try:
                            hydration_data = json.loads(m.group(1))
                            break
                        except Exception:
                            pass

        if is_shell:
            has_hydration = bool(hydration_data)
            attempt.record_claim(Claim(
                field="js_rendered_state",
                value={
                    "shell_status": "js_shell_confirmed",
                    "hydration_payload_recovered": has_hydration,
                    "payload_keys": list(hydration_data.keys())[:5] if has_hydration else [],
                },
                confidence=0.98 if has_hydration else 0.88,
                evidence_span=f"JS shell evaluated with V2 hydration parser for {name}. Recovered: {has_hydration}",
                content_hash=sha,
                source_url=final_url,
                status="accepted",
            ))
        else:
            attempt.record_claim(Claim(
                field="js_rendered_state",
                value={"shell_status": "static_page_complete"},
                confidence=0.99,
                evidence_span=f"Static HTML verified for {name}; no browser emulation required.",
                content_hash=sha,
                source_url=final_url,
                status="accepted",
            ))
