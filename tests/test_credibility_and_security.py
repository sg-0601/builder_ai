from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

import pytest
from norway_company_agent.live_connectors import (
    fetch_fagfolkguiden_reviews,
    slugify_norwegian_name,
)
from norway_company_agent.news_credibility import (
    detect_clickbait,
    evaluate_news_credibility,
    extract_domain,
    verify_entity_in_headline,
)
from norway_company_agent.social_security import (
    assess_positive_purpose,
    detect_security_threats,
    verify_social_channel_security,
)


# =============================================================================
# 1. News Credibility & Ethics Tests (Vær Varsom-plakaten compliance)
# =============================================================================
def test_trusted_publisher_evaluation():
    result = evaluate_news_credibility(
        title="Equinor ASA rapporterer solide kvartalstall",
        publisher_name="E24",
        publisher_url="https://e24.no",
        source_link="https://e24.no/bors-og-finans/i/123/equinor",
        published_at="2026-03-01T10:00:00Z",
        company_name="Equinor ASA",
    )
    assert result["is_publishable"] is True
    assert result["credibility_score"] >= 0.70
    assert result["credibility_tier"] == "high"
    assert not result["fatal_flags"]


def test_blacklisted_domain_rejected():
    result = evaluate_news_credibility(
        title="Equinor ASA planlegger nye investeringer",
        publisher_name="Medium User",
        publisher_url="https://medium.com",
        source_link="https://medium.com/@fake/equinor",
        published_at="2026-03-01T10:00:00Z",
        company_name="Equinor ASA",
    )
    assert result["is_publishable"] is False
    assert result["credibility_score"] == 0.0
    assert any("blacklisted_source" in flag for flag in result["fatal_flags"])


def test_clickbait_headline_detection():
    flags = detect_clickbait("DU VIL IKKE TRO HVA DETTE SELSKAPET GJORDE!!!")
    assert any("clickbait_phrase" in f for f in flags)
    assert "excessive_exclamation" in flags


def test_unrelated_company_headline_rejected():
    result = evaluate_news_credibility(
        title="Norsk Hydro ASA åpner nytt resirkuleringsanlegg i Høyanger",
        publisher_name="NRK",
        publisher_url="https://nrk.no",
        source_link="https://nrk.no/vestland/hydro-123",
        published_at="2026-03-01T10:00:00Z",
        company_name="Equinor ASA",
    )
    assert result["is_publishable"] is False
    assert "weak_or_ambiguous_entity_reference" in result["reasons"]


# =============================================================================
# 2. Social Profile & Channel Security Tests
# =============================================================================
def test_safe_corporate_social_channel():
    sec = verify_social_channel_security(
        platform="linkedin",
        channel_or_profile_name="Equinor Official",
        target_url="https://linkedin.com/company/equinor",
        company_name="Equinor ASA",
        content_samples=["Official company page for Equinor ASA. Energy and engineering solutions."],
        website_domain="equinor.com",
    )
    assert sec["is_safe"] is True
    assert sec["positive_purpose"] is True
    assert sec["impersonation_risk"] in ("low", "medium")
    assert sec["security_tier"] == "verified_safe_and_authentic"


def test_scam_threat_detection_quarantine():
    sec = verify_social_channel_security(
        platform="telegram",
        channel_or_profile_name="Equinor Free Crypto Airdrop Bot",
        target_url="https://t.me/equinor_free_eth",
        company_name="Equinor ASA",
        content_samples=["Connect wallet now to claim guaranteed profit and free ethereum giveaway!"],
        website_domain="equinor.com",
    )
    assert sec["is_safe"] is False
    assert sec["impersonation_risk"] == "critical"
    assert sec["security_tier"] == "quarantined_threat"
    assert len(sec["quarantine_reasons"]) > 0


# =============================================================================
# 3. Local Directory Reviews (Fagfolkguiden) Tests
# =============================================================================
def test_norwegian_slugification():
    assert slugify_norwegian_name("Byggmester Blå AS") == "byggmester-bla-as"
    assert slugify_norwegian_name("Østlandske Rør & Varme") == "ostlandske-ror-varme"


def test_fagfolkguiden_reviews_mock():
    mock_html = b"""
    <html>
      <head>
        <title>Test Selskap AS - 999888777 - Fagfolkguiden</title>
        <script type="application/ld+json">
        {
          "@context": "https://schema.org",
          "@type": "LocalBusiness",
          "name": "Test Selskap AS",
          "aggregateRating": {
            "@type": "AggregateRating",
            "ratingValue": "4.8",
            "reviewCount": "19"
          }
        }
        </script>
      </head>
      <body>
        <h1>Test Selskap AS</h1>
        <p>Org.nr: 999 888 777</p>
        <a href="https://search.google.com/local/reviews?placeid=ChIJ123">Se anmeldelser</a>
      </body>
    </html>
    """
    mock_resp = MagicMock()
    mock_resp.read.return_value = mock_html
    mock_resp.__enter__.return_value = mock_resp

    with patch("urllib.request.urlopen", return_value=mock_resp):
        profile = {"organisation_number": "999888777", "name": "Test Selskap AS"}
        obs, cost = fetch_fagfolkguiden_reviews(profile)

    assert cost == 0.0
    assert len(obs) == 2
    rev = next(o for o in obs if o["signal_type"] == "review_summary")
    assert rev["metrics"]["rating"] == 4.8
    assert rev["metrics"]["review_count"] == 19
    assert rev["metrics"]["google_review_url"] == "https://search.google.com/local/reviews?placeid=ChIJ123"
