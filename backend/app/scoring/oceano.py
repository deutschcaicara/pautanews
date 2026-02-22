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
    "OCEANO_OFFICIAL_SOURCE": "Information from official source",
}

def calculate_oceano_score(
    evidence_score: float,
    has_tier1_coverage: bool,
    is_official: bool,
    base_weight: float = 5.0
) -> Dict[str, Any]:
    """Calculate SCORE_OCEANO_AZUL with EVIDENCE_MULTIPLIER and COVERAGE_LAG."""
    
    # 1. Evidence Multiplier (§12.2)
    evidence_multiplier = 1.0 + (evidence_score / 5.0)
    
    # 2. Coverage Lag (§12.2)
    # If Tier-1 hasn't covered it yet, we reward it
    lag_boost = 10.0 if not has_tier1_coverage else 0.0
    
    # 3. Official Source (§12.2)
    official_boost = 5.0 if is_official else 0.0
    
    raw_score = (base_weight + official_boost + lag_boost) * evidence_multiplier
    
    final_score = min(raw_score, 100.0) # Cap for sanity
    
    reasons = []
    if evidence_score > 3.0: reasons.append("OCEANO_EVIDENCE_STRONG")
    if not has_tier1_coverage: reasons.append("OCEANO_COVERAGE_LAG")
    if is_official: reasons.append("OCEANO_OFFICIAL_SOURCE")
    
    return {
        "score": round(final_score, 2),
        "reasons": reasons
    }
