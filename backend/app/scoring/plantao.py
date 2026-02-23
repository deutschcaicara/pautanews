"""SCORE_PLANTAO calculation — Blueprint §12.1.

Focuses on velocity, tier weight, and diversity for hard news.
"""
from __future__ import annotations

import math
from datetime import datetime, timezone
from typing import Dict, List, Any

# REASONS_CODES estáveis (§12.2)
REASONS = {
    "PLANTAO_VELOCITY_SPIKE": "Velocity spike detected",
    "PLANTAO_TIER_WEIGHT": "High-tier source weight",
    "PLANTAO_DIVERSITY": "Multiple independent sources",
    "PLANTAO_IMPACT_HEURISTIC": "Weak impact heuristic signal",
    "PLANTAO_TRUST_PENALTY": "Trust penalty applied",
    "PLANTAO_DECAY": "Exponential decay applied",
}

def calculate_plantao_score(
    tier: int,
    velocity: float,
    source_count: int,
    first_seen_at: datetime,
    impact_signal: float = 0.0,
    trust_penalty: float = 0.0,
    base_weight: float = 10.0
) -> Dict[str, Any]:
    """Calculate SCORE_PLANTAO with exponential decay."""
    # 1. Tier weight (Inverse linear)
    tier_weight = (4 - tier) * 2.0  # Tier 1 = 6.0, Tier 3 = 2.0
    
    # 2. Velocity (logarithmic scaling)
    velocity_boost = math.log1p(velocity) * 5.0
    
    # 3. Diversity (sqrt scaling)
    diversity_boost = math.sqrt(source_count) * 3.0
    
    impact_boost = max(0.0, min(10.0, float(impact_signal))) * 0.8

    raw_score = base_weight + tier_weight + velocity_boost + diversity_boost + impact_boost
    raw_score -= max(0.0, min(20.0, float(trust_penalty)))
    
    # 4. Decay (Blueprint §12.1)
    # Decay half-life: 2 hours
    age_hours = (datetime.now(timezone.utc) - first_seen_at).total_seconds() / 3600
    decay_factor = math.exp(-age_hours / 2.0)
    
    final_score = raw_score * decay_factor
    
    reasons = []
    if velocity > 5: reasons.append("PLANTAO_VELOCITY_SPIKE")
    if tier == 1: reasons.append("PLANTAO_TIER_WEIGHT")
    if source_count > 2: reasons.append("PLANTAO_DIVERSITY")
    if impact_boost > 0.5: reasons.append("PLANTAO_IMPACT_HEURISTIC")
    if trust_penalty > 0.0: reasons.append("PLANTAO_TRUST_PENALTY")
    if decay_factor < 0.8: reasons.append("PLANTAO_DECAY")
    
    return {
        "score": round(final_score, 2),
        "reasons": reasons
    }
