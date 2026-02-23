"""Health and Anti-fragility monitoring — Blueprint §6.3 / §11.3.

Detects DATA_STARVATION and source yield collapse.
"""
from __future__ import annotations

import logging
import json
from collections import deque
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List

from app.config import settings
from app.metrics import DATA_STARVATION_INCIDENTS_TOTAL

logger = logging.getLogger(__name__)

class YieldMonitor:
    """Monitors anchor/evidence yield per source (§11.3/§19)."""

    def __init__(self):
        # Local fallback (process-local). Redis is used when available.
        self._baselines: dict[int, deque[dict[str, Any]]] = {}
        self._redis = None
        try:
            import redis  # type: ignore
            self._redis = redis.Redis.from_url(settings.REDIS_URL, decode_responses=True)
        except Exception:
            self._redis = None

    def update_yield(self, source_id: int, anchors_count: int, *, status_code: int = 200):
        """Record latest yield for a fetch."""
        point = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "anchors_count": int(max(0, anchors_count)),
            "status_code": int(status_code),
        }
        if self._redis is not None:
            key = f"radar:yield:{source_id}"
            try:
                self._redis.rpush(key, json.dumps(point, ensure_ascii=True))
                self._redis.ltrim(key, -500, -1)
                self._redis.expire(key, 60 * 60 * 72)
                return
            except Exception as e:
                logger.warning(f"YieldMonitor redis write failed for source {source_id}: {e}")

        bucket = self._baselines.setdefault(source_id, deque(maxlen=500))
        bucket.append(point)

    def check_starvation(
        self,
        source_id: int,
        last_200_ok_window_mins: int = 60,
        *,
        calendar_profile: str | None = None,
    ) -> bool:
        """
        Blueprint §6.3: DATA_STARVATION
        Detect if 200 OK but yield of anchors/evidências collapses for the window.
        """
        now = datetime.now(timezone.utc)
        window_cutoff = now - timedelta(minutes=last_200_ok_window_mins)

        history: list[dict[str, Any]] = []
        if self._redis is not None:
            key = f"radar:yield:{source_id}"
            try:
                rows = self._redis.lrange(key, 0, -1)
                history = [json.loads(row) for row in rows or []]
            except Exception as e:
                logger.warning(f"YieldMonitor redis read failed for source {source_id}: {e}")
        if not history:
            history = list(self._baselines.get(source_id, []))

        if not history:
            return False

        recent = []
        older = []
        for row in history:
            try:
                ts = datetime.fromisoformat(str(row.get("ts")))
            except Exception:
                continue
            payload = {
                "ts": ts,
                "anchors_count": int(row.get("anchors_count") or 0),
                "status_code": int(row.get("status_code") or 0),
            }
            if ts >= window_cutoff:
                recent.append(payload)
            else:
                older.append(payload)

        if len(recent) < 5:
            return False
        recent_200 = [r for r in recent if r["status_code"] == 200]
        if len(recent_200) < 5:
            return False

        recent_avg = sum(r["anchors_count"] for r in recent_200) / max(len(recent_200), 1)
        historical_200 = [r for r in older if r["status_code"] == 200]
        if len(historical_200) < 10:
            # fallback rule before baseline matures
            return all(r["anchors_count"] == 0 for r in recent_200)

        historical_avg = sum(r["anchors_count"] for r in historical_200) / max(len(historical_200), 1)
        rolling_collapse = (recent_avg <= 0.1 and historical_avg >= 1.0)
        if rolling_collapse:
            return True

        # Optional calendar-aware baseline (Blueprint mentions rolling + calendário).
        if calendar_profile:
            same_hour = now.hour
            is_weekend = now.weekday() >= 5
            if calendar_profile == "business_hours_br" and (is_weekend or not (7 <= same_hour <= 20)):
                # Outside business hours we rely on rolling only to avoid noisy starvation.
                return False

            if calendar_profile == "business_hours_br":
                calendar_baseline = [
                    r for r in historical_200
                    if r["ts"].hour == same_hour and ((r["ts"].weekday() >= 5) == is_weekend)
                ]
            else:
                calendar_baseline = [r for r in historical_200 if r["ts"].hour == same_hour]
            if len(calendar_baseline) >= 8:
                calendar_avg = sum(r["anchors_count"] for r in calendar_baseline) / len(calendar_baseline)
                # "Collapse" relative to expected same-slot yield.
                if calendar_avg >= 1.0 and recent_avg <= max(0.1, calendar_avg * 0.1):
                    return True

        return False

def trigger_starvation_incident(source_id: int, domain: str):
    """Blueprint §6.3: abrir incidente 'DATA_STARVATION'."""
    logger.error(
        f"DATA_STARVATION: Possível quebra de layout/API em {domain} (ID: {source_id})",
        extra={
            "incident_code": "DATA_STARVATION",
            "source_domain": domain,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
    )
    DATA_STARVATION_INCIDENTS_TOTAL.labels(source_domain=(domain or "unknown")[:255]).inc()
    # emit_alert(channel="ops", ...)


yield_monitor = YieldMonitor()
