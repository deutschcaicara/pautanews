"""SCORE_OCEANO_AZUL calculation — Blueprint §12.2.

Focuses on deterministic evidence and coverage gaps.
"""
from __future__ import annotations

import math
from datetime import datetime, timezone
from typing import Dict, List, Any

# REASONS_CODES estáveis (§12.2)
REASONS = {
    "OCEANO_EVIDENCE_STRONG": "Strong deterministic anchors found",
    "OCEANO_COVERAGE_LAG": "Tier-1 coverage gap (Oceano Azul)",
    "OCEANO_EVIDENCE_PDF": "PDF evidence detected",
    "OCEANO_TRUST_PENALTY_REDUCED": "Trust penalty reduced due to strong evidence",
    "OCEANO_OFFICIAL_SOURCE": "Information from official source",
}

def calculate_oceano_score(
    evidence_score: float,
    has_tier1_coverage: bool,
    is_official: bool,
    coverage_lag_minutes: float | None = None,
    has_pdf_evidence: bool = False,
    trust_penalty: float = 0.0,
    base_weight: float = 5.0
) -> Dict[str, Any]:
    """Calculate SCORE_OCEANO_AZUL with EVIDENCE_MULTIPLIER and COVERAGE_LAG."""
    
    # 1. Evidence Multiplier (§12.2)
    evidence_multiplier = 1.0 + (evidence_score / 5.0)
    
    # 2. Coverage Lag (§12.2)
    # If Tier-1 hasn't covered it yet, we reward it
    if coverage_lag_minutes is None:
        lag_boost = 10.0 if not has_tier1_coverage else 0.0
    else:
        lag_boost = min(20.0, max(0.0, float(coverage_lag_minutes)) / 6.0) if not has_tier1_coverage else 0.0

    # 3. Official Source (§12.2)
    official_boost = 5.0 if is_official else 0.0
    pdf_boost = 4.0 if has_pdf_evidence else 0.0

    # Trust penalty is reduced under strong evidence (Blueprint §12.2)
    effective_trust_penalty = max(0.0, float(trust_penalty)) * (0.25 if evidence_score >= 3.0 else 0.6)

    raw_score = (base_weight + official_boost + lag_boost + pdf_boost) * evidence_multiplier
    raw_score -= effective_trust_penalty
    
    final_score = min(raw_score, 100.0) # Cap for sanity
    
    reasons = []
    if evidence_score > 3.0: reasons.append("OCEANO_EVIDENCE_STRONG")
    if not has_tier1_coverage: reasons.append("OCEANO_COVERAGE_LAG")
    if has_pdf_evidence: reasons.append("OCEANO_EVIDENCE_PDF")
    if effective_trust_penalty > 0 and evidence_score >= 3.0: reasons.append("OCEANO_TRUST_PENALTY_REDUCED")
    if is_official: reasons.append("OCEANO_OFFICIAL_SOURCE")
    
    return {
        "score": round(final_score, 2),
        "reasons": reasons
    }
