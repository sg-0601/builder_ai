"""Base classes and typed models for the Signalpost Strategy Registry."""

from __future__ import annotations

import hashlib
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


@dataclass
class Claim:
    """Represents a discrete candidate or accepted factual assertion."""
    field: str
    value: Any
    confidence: float
    evidence_span: str
    content_hash: str
    source_url: str
    status: str = "accepted"  # "accepted" or "rejected"
    rejection_reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class RawSnapshot:
    """Preserves raw immutable response snapshots."""
    url: str
    content_hash: str
    status_code: int
    content_type: str
    byte_count: int
    retrieved_at: str
    excerpt: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class StrategyAttempt:
    """Captures the complete provenance and metrics of a single strategy execution.
    
    Adheres strictly to Signalpost Learning Harness requirements:
    - strategy name and version
    - input organisation number
    - requested URLs and redirect chain
    - raw snapshot hashes
    - candidate domains, profiles and claims
    - accepted and rejected claims with reasons
    - exact-identity evidence
    - runtime, request count and cost
    - errors and availability states
    """
    strategy_name: str
    strategy_version: str
    organisation_number: str
    requested_urls: list[str] = field(default_factory=list)
    redirect_chain: list[str] = field(default_factory=list)
    raw_snapshot_hashes: list[str] = field(default_factory=list)
    candidate_domains: list[str] = field(default_factory=list)
    profiles: list[dict[str, Any]] = field(default_factory=list)
    claims: list[Claim] = field(default_factory=list)
    accepted_claims: list[Claim] = field(default_factory=list)
    rejected_claims: list[Claim] = field(default_factory=list)
    exact_identity_evidence: list[dict[str, Any]] = field(default_factory=list)
    runtime_ms: int = 0
    request_count: int = 0
    cost_usd: float = 0.0
    errors: list[str] = field(default_factory=list)
    availability_state: str = "success"  # "success", "partial", "unavailable", "failed"
    attempt_timestamp: str = field(default_factory=utc_now)

    def record_claim(self, claim: Claim) -> None:
        self.claims.append(claim)
        if claim.status == "accepted":
            self.accepted_claims.append(claim)
        else:
            self.rejected_claims.append(claim)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["claims"] = [c.to_dict() if hasattr(c, "to_dict") else c for c in self.claims]
        data["accepted_claims"] = [c.to_dict() if hasattr(c, "to_dict") else c for c in self.accepted_claims]
        data["rejected_claims"] = [c.to_dict() if hasattr(c, "to_dict") else c for c in self.rejected_claims]
        return data


class BaseStrategy:
    """Abstract base class for all registered discovery and extraction routes."""

    name: str = "base_strategy"
    version: str = "1.0.0"

    def execute(self, company: dict[str, Any], **kwargs: Any) -> StrategyAttempt:
        """Executes the strategy and returns a fully populated StrategyAttempt."""
        start_time = time.monotonic()
        attempt = StrategyAttempt(
            strategy_name=self.name,
            strategy_version=self.version,
            organisation_number=str(company.get("organisation_number") or ""),
        )

        try:
            self._run(company, attempt, **kwargs)
        except Exception as exc:
            attempt.errors.append(f"{type(exc).__name__}: {str(exc)[:200]}")
            attempt.availability_state = "failed"
        finally:
            attempt.runtime_ms = int((time.monotonic() - start_time) * 1000)

        return attempt

    def _run(self, company: dict[str, Any], attempt: StrategyAttempt, **kwargs: Any) -> None:
        """Subclasses must implement extraction logic here."""
        raise NotImplementedError
