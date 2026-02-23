from __future__ import annotations

import enum
from typing import Optional, Dict, Any

from pydantic import BaseModel, Field, field_validator


class PoolType(str, enum.Enum):
    FAST_POOL = "FAST_POOL"
    HEAVY_RENDER_POOL = "HEAVY_RENDER_POOL"
    DEEP_EXTRACT_POOL = "DEEP_EXTRACT_POOL"


class StrategyType(str, enum.Enum):
    RSS = "RSS"
    HTML = "HTML"
    API = "API"
    SPA_API = "SPA_API"
    SPA_HEADLESS = "SPA_HEADLESS"
    PDF = "PDF"


class Cadence(BaseModel):
    cron: Optional[str] = None
    interval_seconds: Optional[int] = None

    @field_validator("cron")
    @classmethod
    def validate_cron(cls, v: str | None) -> str | None:
        if v and len(v.split()) != 5:
            raise ValueError("Cron must have 5 fields")
        return v


class Limits(BaseModel):
    rate_limit_req_per_min: int = Field(default=10, ge=1)
    concurrency_per_domain: int = Field(default=1, ge=1)
    timeout_seconds: int = Field(default=30, ge=1)
    max_bytes: int = Field(default=5_000_000, ge=1024)


class Observability(BaseModel):
    starvation_window_hours: int = Field(default=24, ge=1)
    yield_keys: list[str] = Field(default_factory=list)
    baseline_rolling: bool = True
    calendar_profile: Optional[str] = None


class SourceProfile(BaseModel):
    """Source Profile DSL (Blueprint §6)."""

    id: Optional[int] = None
    source_id: str
    source_domain: Optional[str] = None
    tier: int = Field(ge=1, le=3)
    is_official: bool = False
    lang: str = "pt-BR"
    pool: PoolType
    strategy: StrategyType
    endpoints: Dict[str, str]
    headers: Dict[str, str] = Field(default_factory=dict)
    cadence: Cadence
    limits: Limits = Field(default_factory=Limits)
    observability: Observability = Field(default_factory=Observability)
    metadata: Dict[str, Any] = Field(default_factory=dict)

    @field_validator("endpoints")
    @classmethod
    def validate_endpoints(cls, v: Dict[str, str]) -> Dict[str, str]:
        if not v:
            raise ValueError("At least one endpoint must be defined")
        return v
