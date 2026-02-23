"""Structured Delta Generation — Blueprint §15.

Identifies 'what changed' between event states or documents.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Dict, Any, List, Optional

def generate_anchor_delta(old_anchors: List[str], new_anchors: List[str]) -> Dict[str, Any]:
    """§15: AnchorDelta."""
    added = set(new_anchors) - set(old_anchors)
    removed = set(old_anchors) - set(new_anchors)
    return {
        "added": list(added),
        "removed": list(removed)
    }

def generate_value_delta(old_value: float | None, new_value: float | None) -> Dict[str, Any]:
    """§15: ValueDelta."""
    if old_value == new_value:
        return {}
    return {
        "from": old_value,
        "to": new_value,
        "diff": (new_value or 0) - (old_value or 0)
    }

def generate_temporal_delta(old_time: datetime | None, new_time: datetime | None) -> Dict[str, Any]:
    """§15: TemporalDelta."""
    if old_time == new_time:
        return {}
    return {
        "previous_time": old_time.isoformat() if old_time else None,
        "new_time": new_time.isoformat() if new_time else None,
        "is_postponed": new_time > old_time if (new_time and old_time) else None
    }


def generate_entity_delta(old_entities: List[str], new_entities: List[str]) -> Dict[str, Any]:
    """§15: EntityDelta (MVP representation using normalized entity keys)."""
    added = sorted(set(new_entities) - set(old_entities))
    removed = sorted(set(old_entities) - set(new_entities))
    if not added and not removed:
        return {}
    return {
        "added": added,
        "removed": removed,
    }

def generate_full_delta(old_doc: Dict[str, Any], new_doc: Dict[str, Any]) -> Dict[str, Any]:
    """Generate all structured deltas for a document update."""
    return {
        "anchors": generate_anchor_delta(old_doc.get("anchors", []), new_doc.get("anchors", [])),
        "values": generate_value_delta(old_doc.get("value"), new_doc.get("value")),
        "entities": generate_entity_delta(old_doc.get("entities", []), new_doc.get("entities", [])),
        "temporal": generate_temporal_delta(old_doc.get("time"), new_doc.get("time")),
        "timestamp": datetime.now(timezone.utc).isoformat()
    }
