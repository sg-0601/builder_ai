"""Central Strategy Registry for the Signalpost Learning Harness."""

from __future__ import annotations

from typing import Any

from strategies.base import BaseStrategy
from strategies.browser_fallback import BrowserFallbackV1Strategy, BrowserFallbackV2Strategy
from strategies.decision_table_router import DecisionTableRouterStrategy, DecisionTableRouterV2Strategy
from strategies.jsonld_opengraph import JsonLdOpenGraphStrategy
from strategies.leader_founder_bridge import LeaderFounderBridgeStrategy
from strategies.pdf_fallback import PdfFallbackStrategy
from strategies.registry_site import RegistrySiteStrategy
from strategies.search_candidates import SearchCandidatesStrategy
from strategies.sitemap_static import SitemapStaticStrategy
from strategies.static_homepage import StaticHomepageStrategy
from strategies.targeted_paths import TargetedPathsStrategy


class StrategyRegistry:
    """Registry maintaining all stable versioned discovery and extraction routes.
    
    Adheres strictly to the Signalpost Learning Harness specification:
    1. registry-provided website (registry_site)
    2. sitemap and robots discovery (sitemap_static)
    3. static homepage crawl (static_homepage_crawl)
    4. targeted /about, /contact, /leadership, /locations, /careers, /news paths (targeted_paths)
    5. JSON-LD and OpenGraph extraction (jsonld_opengraph)
    6. search-provider candidate discovery (search_candidates)
    7. leader/founder bridge from official role to public brand (leader_founder_bridge)
    8. browser-rendered fallback for confirmed JavaScript shell (browser_fallback v1 & v2)
    9. annual-account PDF fallback (pdf_fallback)
    10. Decision table router (decision_table_router)
    """

    def __init__(self) -> None:
        self._strategies: dict[str, BaseStrategy] = {}
        self._register_defaults()

    def _register_defaults(self) -> None:
        defaults = [
            RegistrySiteStrategy(),
            SitemapStaticStrategy(),
            StaticHomepageStrategy(),
            TargetedPathsStrategy(),
            JsonLdOpenGraphStrategy(),
            SearchCandidatesStrategy(),
            LeaderFounderBridgeStrategy(),
            BrowserFallbackV1Strategy(),
            BrowserFallbackV2Strategy(),
            PdfFallbackStrategy(),
            DecisionTableRouterStrategy(),
            DecisionTableRouterV2Strategy(),
        ]
        for strat in defaults:
            self.register(strat)

    def register(self, strategy: BaseStrategy) -> None:
        self._strategies[strategy.name] = strategy
        # Also register with version tag, e.g. browser_fallback_v2
        version_tag = f"{strategy.name}_v{strategy.version.split('.')[0]}"
        self._strategies[version_tag] = strategy

    def get(self, name: str) -> BaseStrategy:
        if name not in self._strategies:
            raise KeyError(f"Strategy '{name}' not found in registry. Available: {self.list_strategies()}")
        return self._strategies[name]

    def list_strategies(self) -> list[str]:
        return sorted(list(self._strategies.keys()))


STRATEGY_REGISTRY = StrategyRegistry()
