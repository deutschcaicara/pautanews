"""State Machine and Action Gating — Blueprint §13.

Manages event transitions and pool-based timeouts.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone, timedelta
from typing import Optional

from app.models.event import Event, EventStatus
from app.config import settings

logger = logging.getLogger(__name__)

def evaluate_state_transition(
    event: Event,
    current_pool: str,
    hydration_start_at: Optional[datetime] = None
) -> EventStatus:
    """Determine the next state for an event based on processing status and timeouts (§13.2)."""
    
    if event.status == EventStatus.NEW:
        return EventStatus.HYDRATING

    if event.status == EventStatus.HYDRATING:
        # Check for hydration timeout (§13.2)
        if hydration_start_at:
            elapsed = (datetime.now(timezone.utc) - hydration_start_at).total_seconds()
            
            # Blueprint §13.2 timeouts
            timeout = settings.SLO_FAST_PATH_S if current_pool == "FAST_POOL" else settings.SLO_RENDER_PATH_S
            
            if elapsed > timeout:
                logger.warning(f"Hydration timeout for event {event.id}. Transitioning to PARTIAL_ENRICH.")
                return EventStatus.PARTIAL_ENRICH

    return event.status

def check_quarantine(event_score_plantao: float, source_count: int) -> bool:
    """Check if an event should enter QUARANTINE (§13.3)."""
    # Simple heuristic: low score but multiple sources = grey area
    if event_score_plantao < 20.0 and source_count >= 2:
        return True
    return False

def check_unverified_viral(velocity: float, source_diversity_count: int) -> bool:
    """Blueprint §13.4: Flag as UNVERIFIED_VIRAL if velocity is extreme."""
    if velocity > 50.0 and source_diversity_count >= 3:
        return True
    return False
