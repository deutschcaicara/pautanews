"""Dynamic Scheduler for Radar Hard News.

This module provides the logic to map database-stored Source profiles
to Celery periodic tasks without requiring hardcoded beat schedules.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone, timedelta

from celery.schedules import crontab
from sqlalchemy import select, func
from app.db import async_session_factory
from app.models.source import Source
from app.models.fetch_attempt import FetchAttempt
from app.schemas.source_profile import SourceProfile

logger = logging.getLogger(__name__)

INSTITUTIONAL_UA = "RadarHardNews/1.0 (Institutional; newsroom monitoring)"


def _parse_cron(expr: str) -> crontab:
    minute, hour, day_of_month, month_of_year, day_of_week = expr.split()
    return crontab(
        minute=minute,
        hour=hour,
        day_of_month=day_of_month,
        month_of_year=month_of_year,
        day_of_week=day_of_week,
    )


async def _last_attempt_at(source_pk: int) -> datetime | None:
    async with async_session_factory() as session:
        result = await session.execute(
            select(func.max(FetchAttempt.attempted_at)).where(FetchAttempt.source_id == source_pk)
        )
        return result.scalar()


def _is_due(profile: SourceProfile, last_attempt_at: datetime | None, now_utc: datetime) -> bool:
    cadence = profile.cadence
    if cadence.interval_seconds:
        if last_attempt_at is None:
            return True
        return (now_utc - last_attempt_at).total_seconds() >= cadence.interval_seconds

    if cadence.cron:
        try:
            sched = _parse_cron(cadence.cron)
            reference = last_attempt_at or (now_utc - timedelta(days=1))
            due, _next_in = sched.is_due(reference)
            return bool(due)
        except Exception as exc:
            logger.error("Invalid cron for source %s: %s", profile.source_id, exc)
            return False

    # If cadence is malformed/empty, err on the side of not overfetching.
    return False


async def get_active_source_profiles(*, only_due: bool = True) -> list[SourceProfile]:
    """Fetch enabled sources and validate their profiles."""
    profiles = []
    now_utc = datetime.now(timezone.utc)
    async with async_session_factory() as session:
        result = await session.execute(
            select(Source).where(Source.enabled == True)
        )
        sources = result.scalars().all()

        for source in sources:
            try:
                data = source.fetch_policy_json.copy()
                data["id"] = source.id
                # Canonical DB fields win over partial DSL payloads.
                data.setdefault("source_domain", source.domain)
                data["tier"] = source.tier
                data["is_official"] = source.is_official
                data["lang"] = source.lang
                headers = dict(data.get("headers") or {})
                headers.setdefault("User-Agent", INSTITUTIONAL_UA)
                data["headers"] = headers
                profile = SourceProfile(**data)
                if only_due:
                    last_attempt = await _last_attempt_at(source.id)
                    if not _is_due(profile, last_attempt, now_utc):
                        continue
                profiles.append(profile)
            except Exception as e:
                logger.error(f"Invalid profile for source {source.id} ({source.domain}): {e}")
    
    return profiles

def schedule_fetches(celery_app):
    """
    In a real-world scenario with django-celery-beat or equivalent, 
    we would update the PeriodicTask table here.
    For this MVP, we will use a dedicated beat task that orchestrates 
    the fan-out of fetch jobs based on current DB state.
    """
    # This will be called by the orchestrator task defined in app/workers/orchestrator.py
    return None
