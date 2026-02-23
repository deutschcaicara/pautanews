"""State Machine and Action Gating — Blueprint §13.

Manages event transitions and pool-based timeouts.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

from app.models.event import Event, EventStatus
from app.config import settings

logger = logging.getLogger(__name__)


def _status_name(value: EventStatus | str) -> str:
    if isinstance(value, EventStatus):
        return value.value
    raw = str(value)
    if raw.startswith("EventStatus."):
        return raw.split(".", 1)[1]
    return raw

def evaluate_state_transition(
    event: Event,
    current_pool: str,
    hydration_start_at: Optional[datetime] = None
) -> EventStatus:
    """Determine the next state for an event based on processing status and timeouts (§13.2)."""
    
    if _status_name(event.status) == EventStatus.NEW.value:
        return EventStatus.HYDRATING

    if _status_name(event.status) == EventStatus.HYDRATING.value:
        # Check for hydration timeout (§13.2)
        if hydration_start_at:
            elapsed = (datetime.now(timezone.utc) - hydration_start_at).total_seconds()
            
            # Blueprint §13.2 timeouts
            timeout = (
                settings.HYDRATION_TIMEOUT_FAST_S
                if current_pool == "FAST_POOL"
                else settings.HYDRATION_TIMEOUT_RENDER_S
            )
            
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


def action_gating_decision(
    event: Event,
    *,
    action: str,
    current_pool: str = "FAST_POOL",
    now_utc: Optional[datetime] = None,
) -> tuple[bool, str | None]:
    """Editorial action gating (Blueprint §13.2/§13.6 style MVP).

    Returns `(allowed, reason_code_if_blocked)`.
    """
    action = str(action or "").upper()
    now = now_utc or datetime.now(timezone.utc)
    status = _status_name(event.status)

    if status == EventStatus.MERGED.value:
        return False, "ACTION_BLOCKED_MERGED_TOMBSTONE"
    if status in {EventStatus.IGNORED.value, EventStatus.EXPIRED.value} and action in {"MERGE", "SPLIT", "PAUTAR"}:
        return False, f"ACTION_BLOCKED_{status}"

    if status == EventStatus.HYDRATING.value and action in {"MERGE", "SPLIT", "PAUTAR"}:
        hydration_start = getattr(event, "first_seen_at", None) or now
        next_state = evaluate_state_transition(
            event,
            current_pool=current_pool,
            hydration_start_at=hydration_start,
        )
        if next_state == EventStatus.HYDRATING:
            return False, "ACTION_BLOCKED_HYDRATING"

    return True, None
