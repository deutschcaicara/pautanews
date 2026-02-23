from __future__ import annotations

from datetime import datetime, timezone, timedelta

from app.models.event import EventDoc
from app.split_service import _ensure_single_primary, _normalize_doc_ids, _status_name


def _rel(doc_id: int, *, primary: bool, seen_offset_s: int) -> EventDoc:
    r = EventDoc()
    r.event_id = 1
    r.doc_id = doc_id
    r.source_id = 1
    r.is_primary = primary
    r.seen_at = datetime.now(timezone.utc) + timedelta(seconds=seen_offset_s)
    return r


def test_normalize_doc_ids_dedupes_and_filters_invalid() -> None:
    assert _normalize_doc_ids([1, "2", "x", 2, -1, 0, "3"]) == [1, 2, 3]


def test_ensure_single_primary_keeps_only_one_primary() -> None:
    rels = [_rel(1, primary=True, seen_offset_s=0), _rel(2, primary=True, seen_offset_s=1)]
    _ensure_single_primary(rels)
    assert sum(1 for r in rels if r.is_primary) == 1


def test_ensure_single_primary_promotes_oldest_when_none() -> None:
    rels = [_rel(10, primary=False, seen_offset_s=10), _rel(11, primary=False, seen_offset_s=0)]
    _ensure_single_primary(rels)
    assert sum(1 for r in rels if r.is_primary) == 1
    assert next(r for r in rels if r.is_primary).doc_id == 11


def test_status_name_handles_enum_string_repr() -> None:
    assert _status_name("EventStatus.MERGED") == "MERGED"

