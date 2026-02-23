from datetime import datetime, timedelta, timezone

from app.scoring.oceano import calculate_oceano_score
from app.scoring.plantao import calculate_plantao_score


def test_plantao_score_includes_reasons_and_bounds() -> None:
    first_seen = datetime.now(timezone.utc) - timedelta(minutes=5)
    data = calculate_plantao_score(
        tier=1,
        velocity=8.0,
        source_count=4,
        first_seen_at=first_seen,
        impact_signal=4.0,
        trust_penalty=1.0,
    )
    assert 0 <= data["score"] <= 100
    assert "PLANTAO_TIER_WEIGHT" in data["reasons"]
    assert "PLANTAO_VELOCITY_SPIKE" in data["reasons"]


def test_oceano_score_rewards_lag_and_pdf() -> None:
    low = calculate_oceano_score(
        evidence_score=1.0,
        has_tier1_coverage=True,
        is_official=False,
        coverage_lag_minutes=0,
        has_pdf_evidence=False,
        trust_penalty=2.0,
    )
    high = calculate_oceano_score(
        evidence_score=4.0,
        has_tier1_coverage=False,
        is_official=True,
        coverage_lag_minutes=120,
        has_pdf_evidence=True,
        trust_penalty=2.0,
    )
    assert high["score"] > low["score"]
    assert "OCEANO_COVERAGE_LAG" in high["reasons"]
    assert "OCEANO_EVIDENCE_PDF" in high["reasons"]

