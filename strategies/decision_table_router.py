"""Decision Table Router Strategy (decision_table_router_v1).

Implements the official Signalpost Learning Harness Decision Table:
1. Static HTML first (registry_site + static_homepage_crawl)
2. Browser rendering fallback only after a JavaScript-shell test confirms dynamic rendering is needed
3. PDF layout / annual accounts parsing fallback when plain text fails or no website exists
4. Search provider candidate discovery when official website is unlisted
"""

from __future__ import annotations

import time
from typing import Any

from strategies.base import BaseStrategy, Claim, StrategyAttempt
from strategies.browser_fallback import BrowserFallbackV2Strategy, is_javascript_shell
from strategies.pdf_fallback import PdfFallbackStrategy
from strategies.registry_site import RegistrySiteStrategy
from strategies.search_candidates import SearchCandidatesStrategy
from strategies.static_homepage import StaticHomepageStrategy


class DecisionTableRouterStrategy(BaseStrategy):
    """Decision Table Router implementing the hierarchical routing policy."""
    name = "decision_table_router"
    version = "1.0.0"

    def __init__(self) -> None:
        self.registry_site = RegistrySiteStrategy()
        self.static_homepage = StaticHomepageStrategy()
        self.browser_fallback = BrowserFallbackV2Strategy()
        self.pdf_fallback = PdfFallbackStrategy()
        self.search_candidates = SearchCandidatesStrategy()

    def _run(self, company: dict[str, Any], attempt: StrategyAttempt, **kwargs: Any) -> None:
        org = str(company.get("organisation_number") or "")
        name = str(company.get("name") or "")
        raw_website = str(company.get("website") or "").strip()

        routing_steps: list[str] = []

        # Branch A: Company has declared website -> Try Static HTML First
        if raw_website:
            routing_steps.append("step_1_static_html_probe")
            static_att = self.registry_site.execute(company)
            attempt.requested_urls.extend(static_att.requested_urls)
            attempt.redirect_chain.extend(static_att.redirect_chain)
            attempt.raw_snapshot_hashes.extend(static_att.raw_snapshot_hashes)
            attempt.request_count += static_att.request_count
            attempt.cost_usd += static_att.cost_usd
            attempt.claims.extend(static_att.claims)
            attempt.accepted_claims.extend(static_att.accepted_claims)
            attempt.rejected_claims.extend(static_att.rejected_claims)
            attempt.exact_identity_evidence.extend(static_att.exact_identity_evidence)

            # Step 2: JavaScript Shell Test
            # If static website succeeded, check if it requires browser rendering fallback
            routing_steps.append("step_2_javascript_shell_test")
            browser_att = self.browser_fallback.execute(company)
            attempt.requested_urls.extend(browser_att.requested_urls)
            attempt.raw_snapshot_hashes.extend(browser_att.raw_snapshot_hashes)
            attempt.request_count += browser_att.request_count
            attempt.cost_usd += browser_att.cost_usd

            is_js_shell = any(
                c.field in {"js_rendered_state", "js_shell_detected"} and
                isinstance(c.value, dict) and
                c.value.get("shell_status") == "js_shell_confirmed"
                for c in browser_att.claims
            )

            if is_js_shell:
                routing_steps.append("step_2b_browser_fallback_engaged")
                attempt.claims.extend(browser_att.claims)
                attempt.accepted_claims.extend(browser_att.accepted_claims)
                attempt.rejected_claims.extend(browser_att.rejected_claims)
            else:
                routing_steps.append("step_2c_static_html_confirmed_complete")

        # Branch B: No website or static failed -> PDF layout parsing / Search fallback
        else:
            routing_steps.append("step_1b_no_website_declared")

            # Try PDF layout parsing for official annual accounts
            routing_steps.append("step_3_pdf_annual_accounts_fallback")
            pdf_att = self.pdf_fallback.execute(company)
            attempt.requested_urls.extend(pdf_att.requested_urls)
            attempt.raw_snapshot_hashes.extend(pdf_att.raw_snapshot_hashes)
            attempt.request_count += pdf_att.request_count
            attempt.cost_usd += pdf_att.cost_usd
            attempt.claims.extend(pdf_att.claims)
            attempt.accepted_claims.extend(pdf_att.accepted_claims)
            attempt.rejected_claims.extend(pdf_att.rejected_claims)

            # Try search candidates discovery
            routing_steps.append("step_4_search_candidates_discovery")
            search_att = self.search_candidates.execute(company)
            attempt.requested_urls.extend(search_att.requested_urls)
            attempt.raw_snapshot_hashes.extend(search_att.raw_snapshot_hashes)
            attempt.request_count += search_att.request_count
            attempt.cost_usd += search_att.cost_usd
            attempt.claims.extend(search_att.claims)
            attempt.accepted_claims.extend(search_att.accepted_claims)
            attempt.rejected_claims.extend(search_att.rejected_claims)
            attempt.exact_identity_evidence.extend(search_att.exact_identity_evidence)

        # Record Decision Table routing provenance
        attempt.exact_identity_evidence.append({
            "type": "decision_table_routing_trace",
            "has_website": bool(raw_website),
            "routing_steps": routing_steps,
        })
        attempt.availability_state = "success" if attempt.accepted_claims else "partial"
