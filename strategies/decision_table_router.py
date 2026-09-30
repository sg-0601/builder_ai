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
from strategies.jsonld_opengraph import JsonLdOpenGraphStrategy
from strategies.leader_founder_bridge import LeaderFounderBridgeStrategy
from strategies.pdf_fallback import PdfFallbackStrategy
from strategies.registry_site import RegistrySiteStrategy
from strategies.search_candidates import SearchCandidatesStrategy
from strategies.sitemap_static import SitemapStaticStrategy
from strategies.static_homepage import StaticHomepageStrategy
from strategies.targeted_paths import TargetedPathsStrategy


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

            # Extract full homepage content if static probe succeeded
            hp_att = self.static_homepage.execute(company)
            attempt.requested_urls.extend(hp_att.requested_urls)
            attempt.raw_snapshot_hashes.extend(hp_att.raw_snapshot_hashes)
            attempt.request_count += hp_att.request_count
            attempt.claims.extend(hp_att.claims)
            attempt.accepted_claims.extend(hp_att.accepted_claims)
            attempt.rejected_claims.extend(hp_att.rejected_claims)

            # Step 2: JavaScript Shell Test
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

        # Branch B: No website declared -> Search candidates discovery fallback
        else:
            routing_steps.append("step_1b_no_website_declared")
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

        # Official annual accounts fallback (available for all registered entities)
        routing_steps.append("step_3_pdf_annual_accounts_fallback")
        pdf_att = self.pdf_fallback.execute(company)
        attempt.requested_urls.extend(pdf_att.requested_urls)
        attempt.raw_snapshot_hashes.extend(pdf_att.raw_snapshot_hashes)
        attempt.request_count += pdf_att.request_count
        attempt.cost_usd += pdf_att.cost_usd
        attempt.claims.extend(pdf_att.claims)
        attempt.accepted_claims.extend(pdf_att.accepted_claims)
        attempt.rejected_claims.extend(pdf_att.rejected_claims)

        # Record Decision Table routing provenance
        attempt.exact_identity_evidence.append({
            "type": "decision_table_routing_trace",
            "has_website": bool(raw_website),
            "routing_steps": routing_steps,
        })
        attempt.availability_state = "success" if attempt.accepted_claims else "partial"


class DecisionTableRouterV2Strategy(BaseStrategy):
    """Decision Table Router V2 incorporating all 9 organizer routes into a unified decision table."""
    name = "decision_table_router_v2"
    version = "2.0.0"

    def __init__(self) -> None:
        self.registry_site = RegistrySiteStrategy()
        self.static_homepage = StaticHomepageStrategy()
        self.jsonld_opengraph = JsonLdOpenGraphStrategy()
        self.sitemap_static = SitemapStaticStrategy()
        self.targeted_paths = TargetedPathsStrategy()
        self.leader_founder_bridge = LeaderFounderBridgeStrategy()
        self.browser_fallback = BrowserFallbackV2Strategy()
        self.pdf_fallback = PdfFallbackStrategy()
        self.search_candidates = SearchCandidatesStrategy()

    def _run(self, company: dict[str, Any], attempt: StrategyAttempt, **kwargs: Any) -> None:
        org = str(company.get("organisation_number") or "")
        name = str(company.get("name") or "")
        raw_website = str(company.get("website") or "").strip()

        routing_steps: list[str] = []

        # Branch A: Company has declared website -> Hierarchical 9-Route Decision Flow
        if raw_website:
            # 1. Static HTML Probe
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

            raw_bytes = getattr(static_att, "raw_bytes", None)
            html_text = getattr(static_att, "html_text", None)
            final_url = getattr(static_att, "final_url", None)

            # Check if static HTML probe was successful and identity verified
            static_succeeded = bool(static_att.accepted_claims)

            if static_succeeded and raw_bytes and html_text:
                # 2. Static Homepage Clean Content Extraction (In-Memory Reuse)
                routing_steps.append("step_2_static_homepage_content")
                hp_att = self.static_homepage.execute(
                    company, prefetched_bytes=raw_bytes, final_url=final_url
                )
                attempt.requested_urls.extend(hp_att.requested_urls)
                attempt.raw_snapshot_hashes.extend(hp_att.raw_snapshot_hashes)
                attempt.request_count += hp_att.request_count
                attempt.claims.extend(hp_att.claims)
                attempt.accepted_claims.extend(hp_att.accepted_claims)
                attempt.rejected_claims.extend(hp_att.rejected_claims)

                # 3. JSON-LD and OpenGraph Semantic Extraction (In-Memory Reuse)
                routing_steps.append("step_3_jsonld_opengraph_extraction")
                jsonld_att = self.jsonld_opengraph.execute(
                    company, prefetched_bytes=raw_bytes, final_url=final_url
                )
                attempt.requested_urls.extend(jsonld_att.requested_urls)
                attempt.raw_snapshot_hashes.extend(jsonld_att.raw_snapshot_hashes)
                attempt.request_count += jsonld_att.request_count
                attempt.cost_usd += jsonld_att.cost_usd
                attempt.claims.extend(jsonld_att.claims)
                attempt.accepted_claims.extend(jsonld_att.accepted_claims)
                attempt.rejected_claims.extend(jsonld_att.rejected_claims)

                # 4. JavaScript Shell Test & Browser Fallback Decision
                routing_steps.append("step_4_javascript_shell_test")
                browser_att = self.browser_fallback.execute(
                    company, prefetched_bytes=raw_bytes, prefetched_html=html_text, final_url=final_url
                )
                attempt.requested_urls.extend(browser_att.requested_urls)
                attempt.raw_snapshot_hashes.extend(browser_att.raw_snapshot_hashes)
                attempt.request_count += browser_att.request_count
                attempt.cost_usd += browser_att.cost_usd
                attempt.claims.extend(browser_att.claims)
                attempt.accepted_claims.extend(browser_att.accepted_claims)
                attempt.rejected_claims.extend(browser_att.rejected_claims)

                # 5. Targeted Path Probing (In-Memory Contact & Sections Extraction)
                routing_steps.append("step_5_targeted_paths_probing")
                targeted_att = self.targeted_paths.execute(company, prefetched_html=html_text)
                attempt.requested_urls.extend(targeted_att.requested_urls)
                attempt.raw_snapshot_hashes.extend(targeted_att.raw_snapshot_hashes)
                attempt.request_count += targeted_att.request_count
                attempt.cost_usd += targeted_att.cost_usd
                attempt.claims.extend(targeted_att.claims)
                attempt.accepted_claims.extend(targeted_att.accepted_claims)
                attempt.rejected_claims.extend(targeted_att.rejected_claims)

                # 6. Leader/Founder Bridge (In-Memory Role Matching)
                routing_steps.append("step_6_leader_founder_bridge")
                bridge_att = self.leader_founder_bridge.execute(company, prefetched_html=html_text)
                attempt.requested_urls.extend(bridge_att.requested_urls)
                attempt.raw_snapshot_hashes.extend(bridge_att.raw_snapshot_hashes)
                attempt.request_count += bridge_att.request_count
                attempt.cost_usd += bridge_att.cost_usd
                attempt.claims.extend(bridge_att.claims)
                attempt.accepted_claims.extend(bridge_att.accepted_claims)
                attempt.rejected_claims.extend(bridge_att.rejected_claims)

                # 7. Sitemap and Robots Discovery (Fast probe)
                routing_steps.append("step_7_sitemap_static_discovery")
                sitemap_att = self.sitemap_static.execute(company)
                attempt.requested_urls.extend(sitemap_att.requested_urls)
                attempt.raw_snapshot_hashes.extend(sitemap_att.raw_snapshot_hashes)
                attempt.request_count += sitemap_att.request_count
                attempt.cost_usd += sitemap_att.cost_usd
                attempt.claims.extend(sitemap_att.claims)
                attempt.accepted_claims.extend(sitemap_att.accepted_claims)
                attempt.rejected_claims.extend(sitemap_att.rejected_claims)

            else:
                # Plain text website failed or identity rejected!
                # Organizer rule: "PDF layout parsing only when plain text fails."
                routing_steps.append("step_1c_static_failed_engaging_pdf_fallback")
                pdf_att = self.pdf_fallback.execute(company)
                attempt.requested_urls.extend(pdf_att.requested_urls)
                attempt.raw_snapshot_hashes.extend(pdf_att.raw_snapshot_hashes)
                attempt.request_count += pdf_att.request_count
                attempt.cost_usd += pdf_att.cost_usd
                attempt.claims.extend(pdf_att.claims)
                attempt.accepted_claims.extend(pdf_att.accepted_claims)
                attempt.rejected_claims.extend(pdf_att.rejected_claims)

        # Branch B: No website declared -> Search candidates discovery + PDF Fallback
        else:
            routing_steps.append("step_1b_no_website_declared")
            routing_steps.append("step_8_search_candidates_discovery")
            search_att = self.search_candidates.execute(company)
            attempt.requested_urls.extend(search_att.requested_urls)
            attempt.raw_snapshot_hashes.extend(search_att.raw_snapshot_hashes)
            attempt.request_count += search_att.request_count
            attempt.cost_usd += search_att.cost_usd
            attempt.claims.extend(search_att.claims)
            attempt.accepted_claims.extend(search_att.accepted_claims)
            attempt.rejected_claims.extend(search_att.rejected_claims)
            attempt.exact_identity_evidence.extend(search_att.exact_identity_evidence)

            # Plain text website not available, engage official annual accounts fallback
            routing_steps.append("step_9_pdf_annual_accounts_fallback")
            pdf_att = self.pdf_fallback.execute(company)
            attempt.requested_urls.extend(pdf_att.requested_urls)
            attempt.raw_snapshot_hashes.extend(pdf_att.raw_snapshot_hashes)
            attempt.request_count += pdf_att.request_count
            attempt.cost_usd += pdf_att.cost_usd
            attempt.claims.extend(pdf_att.claims)
            attempt.accepted_claims.extend(pdf_att.accepted_claims)
            attempt.rejected_claims.extend(pdf_att.rejected_claims)

        # Record Decision Table routing provenance
        attempt.exact_identity_evidence.append({
            "type": "decision_table_routing_trace_v2",
            "has_website": bool(raw_website),
            "routing_steps": routing_steps,
        })
        attempt.availability_state = "success" if attempt.accepted_claims else "partial"

