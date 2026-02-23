from __future__ import annotations

import enum
from urllib.parse import urlparse
from typing import Optional, Dict, Any

from pydantic import BaseModel, Field, field_validator, model_validator


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
        cleaned: Dict[str, str] = {}
        for key, raw_url in v.items():
            k = str(key).strip()
            url = str(raw_url).strip()
            if not k:
                continue
            if not url:
                raise ValueError(f"Endpoint '{k}' is empty")
            parsed = urlparse(url)
            if parsed.scheme not in {"http", "https"} or not parsed.netloc:
                raise ValueError(f"Endpoint '{k}' must be a valid http(s) URL")
            cleaned[k] = url
        if not cleaned:
            raise ValueError("At least one endpoint must be defined")
        return cleaned

    @field_validator("headers")
    @classmethod
    def validate_headers(cls, v: Dict[str, str]) -> Dict[str, str]:
        return {str(k).strip(): str(val).strip() for k, val in (v or {}).items() if str(k).strip()}

    @field_validator("metadata")
    @classmethod
    def validate_metadata_shape(cls, v: Dict[str, Any]) -> Dict[str, Any]:
        md = dict(v or {})

        for key in ("api_contract", "spa_api_contract"):
            contract = md.get(key)
            if contract is None:
                continue
            if not isinstance(contract, dict):
                raise ValueError(f"metadata.{key} must be an object")
            for field_name in (
                "items_path",
                "title_field",
                "text_field",
                "url_field",
                "published_at_field",
                "modified_at_field",
            ):
                if field_name in contract and contract[field_name] is not None and not isinstance(contract[field_name], str):
                    raise ValueError(f"metadata.{key}.{field_name} must be string")
            for list_field in (
                "title_fields",
                "text_fields",
                "url_fields",
                "canonical_url_fields",
                "author_fields",
                "lang_fields",
                "published_at_fields",
                "modified_at_fields",
            ):
                if list_field in contract and contract[list_field] is not None:
                    if not isinstance(contract[list_field], list) or not all(
                        isinstance(x, str) and str(x).strip() for x in contract[list_field]
                    ):
                        raise ValueError(f"metadata.{key}.{list_field} must be a non-empty list of strings")

        for key in ("api_request", "spa_api_request"):
            req = md.get(key)
            if req is None:
                continue
            if not isinstance(req, dict):
                raise ValueError(f"metadata.{key} must be an object")
            if "method" in req and str(req.get("method", "")).upper() not in {"GET", "POST"}:
                raise ValueError(f"metadata.{key}.method must be GET or POST")
            if "url" in req and req["url"] is not None:
                parsed = urlparse(str(req["url"]))
                if parsed.scheme not in {"http", "https"} or not parsed.netloc:
                    raise ValueError(f"metadata.{key}.url must be a valid http(s) URL")
            for obj_field in ("params", "headers"):
                if obj_field in req and req[obj_field] is not None and not isinstance(req[obj_field], dict):
                    raise ValueError(f"metadata.{key}.{obj_field} must be an object")
            if "json" in req and req["json"] is not None and not isinstance(req["json"], (dict, list)):
                raise ValueError(f"metadata.{key}.json must be object or list")
            if "data" in req and req["data"] is not None and not isinstance(req["data"], (dict, str)):
                raise ValueError(f"metadata.{key}.data must be object or string")

        headless_capture = md.get("headless_capture")
        if headless_capture is not None:
            if not isinstance(headless_capture, dict):
                raise ValueError("metadata.headless_capture must be an object")
            url_contains = headless_capture.get("url_contains")
            if url_contains is not None and not (
                isinstance(url_contains, str)
                or (isinstance(url_contains, list) and all(isinstance(x, str) and str(x).strip() for x in url_contains))
            ):
                raise ValueError("metadata.headless_capture.url_contains must be string or list[str]")

        return md

    @model_validator(mode="after")
    def validate_profile_contract(self) -> "SourceProfile":
        has_interval = self.cadence.interval_seconds is not None
        has_cron = bool(self.cadence.cron)
        if not (has_interval or has_cron):
            raise ValueError("cadence must define interval_seconds or cron")

        endpoint_keys = set(self.endpoints.keys())
        if self.strategy == StrategyType.RSS and "feed" not in endpoint_keys:
            raise ValueError("RSS strategy requires endpoints.feed")
        if self.strategy in {StrategyType.API, StrategyType.SPA_API} and not (
            {"api", "latest", "feed"} & endpoint_keys
        ):
            raise ValueError(f"{self.strategy.value} strategy requires endpoints.api/latest/feed")
        if self.strategy in {StrategyType.HTML, StrategyType.SPA_HEADLESS, StrategyType.PDF} and not (
            {"latest", "feed", "api"} & endpoint_keys
        ):
            raise ValueError(f"{self.strategy.value} strategy requires endpoints.latest/feed/api")

        # Blueprint pool/strategy invariants.
        if self.strategy == StrategyType.SPA_HEADLESS and self.pool != PoolType.HEAVY_RENDER_POOL:
            raise ValueError("SPA_HEADLESS must use HEAVY_RENDER_POOL")
        if self.strategy == StrategyType.SPA_API and self.pool != PoolType.HEAVY_RENDER_POOL:
            raise ValueError("SPA_API must use HEAVY_RENDER_POOL")
        if self.strategy == StrategyType.PDF and self.pool != PoolType.DEEP_EXTRACT_POOL:
            raise ValueError("PDF must use DEEP_EXTRACT_POOL")
        if self.strategy == StrategyType.RSS and self.pool != PoolType.FAST_POOL:
            raise ValueError("RSS must use FAST_POOL")

        # Strategy-specific metadata expectations.
        if self.strategy == StrategyType.SPA_API:
            if not any(k in self.metadata for k in ("spa_api_contract", "api_contract")):
                raise ValueError("SPA_API requires metadata.spa_api_contract (or api_contract)")
        if self.strategy == StrategyType.SPA_HEADLESS:
            if "headless_capture" in self.metadata and not isinstance(self.metadata.get("headless_capture"), dict):
                raise ValueError("SPA_HEADLESS metadata.headless_capture must be object")

        return self
