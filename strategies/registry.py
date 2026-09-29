"""Central Strategy Registry for the Signalpost Learning Harness."""

from __future__ import annotations

from typing import Any

from strategies.base import BaseStrategy
from strategies.browser_fallback import BrowserFallbackV1Strategy, BrowserFallbackV2Strategy
from strategies.pdf_fallback import PdfFallbackStrategy
from strategies.registry_site import RegistrySiteStrategy
from strategies.search_candidates import SearchCandidatesStrategy
from strategies.sitemap_static import SitemapStaticStrategy
from strategies.targeted_paths import TargetedPathsStrategy


class StrategyRegistry:
    """Registry maintaining all stable versioned discovery and extraction routes."""

    def __init__(self) -> None:
        self._strategies: dict[str, BaseStrategy] = {}
        self._register_defaults()

    def _register_defaults(self) -> None:
        defaults = [
            RegistrySiteStrategy(),
            SitemapStaticStrategy(),
            TargetedPathsStrategy(),
            SearchCandidatesStrategy(),
            BrowserFallbackV1Strategy(),
            BrowserFallbackV2Strategy(),
            PdfFallbackStrategy(),
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
