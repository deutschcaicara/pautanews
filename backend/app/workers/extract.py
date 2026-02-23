"""Extraction worker — uses trafilatura/feedparser and JSON contracts.

Implements Blueprint §9.1 step 2 with strategy-specific extraction paths.
"""
from __future__ import annotations

import base64
import hashlib
import json
import logging
from datetime import datetime
from email.utils import parsedate_to_datetime
from typing import Any, Dict

import feedparser
import trafilatura

from app.celery_app import celery
from app.metrics import EXTRACT_ITEMS_TOTAL
from app.schemas.source_profile import SourceProfile, StrategyType
from app.workers.pdf_extractor import extract_pdf_content

logger = logging.getLogger(__name__)

_XHR_START = "<!-- XHR_JSON_CAPTURE_START -->"
_XHR_END = "<!-- XHR_JSON_CAPTURE_END -->"


def _iso_or_none(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.isoformat()
    if hasattr(value, "tm_year"):  # time.struct_time from feedparser
        try:
            return datetime(*value[:6]).isoformat()
        except Exception:
            return None
    if isinstance(value, (int, float)):
        try:
            return datetime.fromtimestamp(float(value)).isoformat()
        except Exception:
            return None
    text = str(value).strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).isoformat()
    except Exception:
        pass
    try:
        return parsedate_to_datetime(text).isoformat()
    except Exception:
        return None


def _deep_get(payload: Any, path: str | None) -> Any:
    if not path:
        return None
    cur = payload
    for raw_part in str(path).split("."):
        if cur is None:
            return None
        part = raw_part.strip()
        if not part:
            continue
        if isinstance(cur, dict):
            cur = cur.get(part)
            continue
        if isinstance(cur, list):
            try:
                idx = int(part)
            except Exception:
                return None
            if idx < 0 or idx >= len(cur):
                return None
            cur = cur[idx]
            continue
        return None
    return cur


def _pick_first(obj: dict[str, Any], keys: list[str]) -> Any:
    for key in keys:
        if key in obj and obj.get(key) not in (None, ""):
            return obj.get(key)
    return None


def _field_candidates(contract: dict[str, Any], plural_key: str, singular_key: str, defaults: list[str]) -> list[str]:
    raw = contract.get(plural_key)
    if raw is None:
        single = contract.get(singular_key)
        if single is None:
            raw = defaults
        elif isinstance(single, list):
            raw = single
        else:
            raw = [single]
    elif isinstance(raw, str):
        raw = [raw]
    return [str(x) for x in raw if x not in (None, "")]


def _extract_xhr_json_blob(raw_body: str) -> str | None:
    if _XHR_START not in raw_body or _XHR_END not in raw_body:
        return None
    try:
        start = raw_body.index(_XHR_START) + len(_XHR_START)
        end = raw_body.index(_XHR_END, start)
    except ValueError:
        return None
    blob = raw_body[start:end].strip()
    return blob or None


def _extract_html_metadata(raw_body: str) -> dict[str, Any]:
    try:
        from selectolax.parser import HTMLParser
    except Exception:
        return {}

    meta: dict[str, Any] = {}
    try:
        tree = HTMLParser(raw_body)
        html = tree.css_first("html")
        if html:
            lang = (html.attributes or {}).get("lang")
            if lang:
                meta["lang"] = str(lang).strip()[:16]

        title_node = tree.css_first("meta[property='og:title']") or tree.css_first("title")
        if title_node:
            if title_node.tag == "meta":
                title = (title_node.attributes or {}).get("content")
            else:
                title = title_node.text()
            if title:
                meta["title"] = str(title).strip()[:2000]

        author_node = (
            tree.css_first("meta[name='author']")
            or tree.css_first("meta[property='article:author']")
        )
        if author_node:
            author = (author_node.attributes or {}).get("content") or author_node.text()
            if author:
                meta["author"] = str(author).strip()[:512]

        canonical_node = tree.css_first("link[rel='canonical']")
        if canonical_node:
            href = (canonical_node.attributes or {}).get("href")
            if href:
                meta["canonical_url"] = str(href).strip()[:2048]

        published_node = (
            tree.css_first("meta[property='article:published_time']")
            or tree.css_first("meta[name='pubdate']")
            or tree.css_first("meta[name='date']")
        )
        if published_node:
            pub_value = (published_node.attributes or {}).get("content") or published_node.text()
            pub_iso = _iso_or_none(pub_value)
            if pub_iso:
                meta["published_at"] = pub_iso

        modified_node = (
            tree.css_first("meta[property='article:modified_time']")
            or tree.css_first("meta[name='lastmod']")
        )
        if modified_node:
            mod_value = (modified_node.attributes or {}).get("content") or modified_node.text()
            mod_iso = _iso_or_none(mod_value)
            if mod_iso:
                meta["modified_at"] = mod_iso
    except Exception as exc:
        logger.debug("HTML metadata extraction failed: %s", exc)
    return meta


def _extract_api_items(
    *,
    profile: SourceProfile,
    raw_body: str,
    content_hash: str,
    fetch_meta: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    try:
        payload = json.loads(raw_body)
    except Exception:
        return []

    contract = {}
    if isinstance(profile.metadata, dict):
        contract = (
            profile.metadata.get("spa_api_contract")
            or profile.metadata.get("api_contract")
            or {}
        )
    if not isinstance(contract, dict):
        contract = {}

    items_node = _deep_get(payload, contract.get("items_path")) if contract.get("items_path") else None
    if items_node is None:
        if isinstance(payload, list):
            items_node = payload
        elif isinstance(payload, dict):
            for candidate in ("items", "results", "data", "rows"):
                maybe = payload.get(candidate)
                if isinstance(maybe, list):
                    items_node = maybe
                    break
            if items_node is None:
                items_node = [payload]
    if not isinstance(items_node, list):
        items_node = [items_node] if items_node is not None else []

    text_fields = _field_candidates(contract, "text_fields", "text_field", [
        "text",
        "body",
        "content",
        "summary",
        "description",
        "titulo",
        "ementa",
    ])
    title_fields = _field_candidates(contract, "title_fields", "title_field", ["title", "titulo", "headline", "name"])
    url_fields = _field_candidates(contract, "url_fields", "url_field", ["url", "link", "href"])
    canonical_url_fields = _field_candidates(contract, "canonical_url_fields", "canonical_url_field", ["canonical_url", "canonicalUrl"])
    author_fields = _field_candidates(contract, "author_fields", "author_field", ["author", "autor", "source_name"])
    lang_fields = _field_candidates(contract, "lang_fields", "lang_field", ["lang", "language", "idioma"])
    published_fields = _field_candidates(contract, "published_at_fields", "published_at_field", [
        "published_at",
        "publishedAt",
        "publication_date",
        "date",
    ])
    modified_fields = _field_candidates(contract, "modified_at_fields", "modified_at_field", [
        "modified_at",
        "updated_at",
        "updatedAt",
        "last_modified",
    ])

    out: list[dict[str, Any]] = []
    for item in items_node:
        if not isinstance(item, dict):
            item = {"value": item}

        chunks: list[str] = []
        for key in text_fields:
            val = _deep_get(item, key) if "." in str(key) else item.get(str(key))
            if val in (None, ""):
                continue
            if isinstance(val, (dict, list)):
                chunks.append(json.dumps(val, ensure_ascii=False))
            else:
                chunks.append(str(val))
        text = "\n\n".join(c.strip() for c in chunks if str(c).strip()).strip()
        if not text:
            text = json.dumps(item, ensure_ascii=False)[:50000]

        url = _pick_first(item, url_fields) or profile.endpoints.get("api") or profile.endpoints.get("latest") or profile.endpoints.get("feed")
        title = _pick_first(item, title_fields)
        canonical_url = _pick_first(item, canonical_url_fields) or url
        author = _pick_first(item, author_fields)
        lang = _pick_first(item, lang_fields) or profile.lang
        published_at = _iso_or_none(_pick_first(item, published_fields))
        modified_at = _iso_or_none(_pick_first(item, modified_fields))
        item_hash = hashlib.sha256(
            f"{title or ''}\n{url or ''}\n{text}".encode("utf-8", errors="ignore")
        ).hexdigest()

        doc_meta = {
            "snapshot_id": (fetch_meta or {}).get("snapshot_id"),
            "canonical_url": canonical_url,
            "author": author,
            "lang": lang,
            "published_at": published_at,
            "modified_at": modified_at,
        }
        out.append(
            {
                "text": text[:50000],
                "url": str(url) if url else None,
                "title": (str(title)[:2000] if title is not None else None),
                "content_hash": item_hash or content_hash,
                "doc_meta": doc_meta,
            }
        )

    return [i for i in out if i.get("text") and i.get("url")]


@celery.task(name="app.workers.extract.run_extraction")
def run_extraction(
    profile_dict: Dict[str, Any],
    raw_body: str,
    content_hash: str,
    payload_kind: str = "text",
    fetch_meta: Dict[str, Any] | None = None,
):
    """Clean text and prepare strategy-specific items for organization."""
    profile = SourceProfile(**profile_dict)
    logger.info("Extracting content for %s", profile.source_id)
    fetch_meta = dict(fetch_meta or {})

    # 1. Extraction strategy based on profile
    items_to_process: list[dict[str, Any]] = []

    if profile.strategy == StrategyType.PDF or payload_kind == "pdf_base64":
        try:
            pdf_bytes = base64.b64decode(raw_body.encode("ascii"))
        except Exception as e:
            logger.error("Failed to decode PDF payload for %s: %s", profile.source_id, e)
            return

        extracted_pdf_text = extract_pdf_content(pdf_bytes)
        item_url = profile.endpoints.get("latest") or profile.endpoints.get("feed") or profile.endpoints.get("api")
        if extracted_pdf_text and item_url:
            items_to_process.append(
                {
                    "text": extracted_pdf_text,
                    "url": item_url,
                    "title": None,
                    "content_hash": content_hash,
                    "doc_meta": {
                        "snapshot_id": fetch_meta.get("snapshot_id"),
                        "canonical_url": item_url,
                        "lang": profile.lang,
                    },
                }
            )

    elif profile.strategy == StrategyType.RSS:
        feed = feedparser.parse(raw_body)
        if not feed.entries:
            logger.warning("Feedparser yielded no entries for %s", profile.source_id)
            return

        feed_lang = (feed.feed.get("language") if getattr(feed, "feed", None) else None) or profile.lang
        logger.info("RSS capture detected %s entries for %s", len(feed.entries), profile.source_id)
        for entry in feed.entries:
            content = entry.get("summary") or entry.get("description") or ""
            item_url = entry.get("link")
            if not item_url:
                continue
            item_hash = hashlib.sha256(
                f"{entry.get('title') or ''}\n{item_url}\n{content}".encode("utf-8")
            ).hexdigest()
            items_to_process.append(
                {
                    "text": content,
                    "url": item_url,
                    "title": entry.get("title"),
                    "content_hash": item_hash,
                    "doc_meta": {
                        "snapshot_id": fetch_meta.get("snapshot_id"),
                        "canonical_url": item_url,
                        "author": entry.get("author"),
                        "lang": entry.get("language") or feed_lang,
                        "published_at": _iso_or_none(entry.get("published_parsed") or entry.get("published")),
                        "modified_at": _iso_or_none(entry.get("updated_parsed") or entry.get("updated")),
                    },
                }
            )

    elif profile.strategy in {StrategyType.API, StrategyType.SPA_API}:
        items_to_process.extend(
            _extract_api_items(
                profile=profile,
                raw_body=raw_body,
                content_hash=content_hash,
                fetch_meta=fetch_meta,
            )
        )
        if not items_to_process:
            # JSON APIs may not parse with trafilatura; keep raw body as fallback.
            item_url = profile.endpoints.get("api") or profile.endpoints.get("latest") or profile.endpoints.get("feed")
            if item_url:
                items_to_process.append(
                    {
                        "text": raw_body[:50000],
                        "url": item_url,
                        "title": None,
                        "content_hash": content_hash,
                        "doc_meta": {
                            "snapshot_id": fetch_meta.get("snapshot_id"),
                            "canonical_url": item_url,
                            "lang": profile.lang,
                        },
                    }
                )

    else:
        # Trafilatura extraction for HTML / SPA_HEADLESS
        extracted = trafilatura.extract(
            raw_body,
            include_comments=False,
            include_tables=True,
            no_fallback=False,
        )
        html_meta = _extract_html_metadata(raw_body)

        if not extracted and profile.strategy == StrategyType.SPA_HEADLESS:
            xhr_blob = _extract_xhr_json_blob(raw_body)
            if xhr_blob:
                extracted = xhr_blob[:50000]

        item_url = (
            html_meta.get("canonical_url")
            or profile.endpoints.get("feed")
            or profile.endpoints.get("latest")
            or profile.endpoints.get("api")
        )
        if extracted and item_url:
            items_to_process.append(
                {
                    "text": extracted,
                    "url": item_url,
                    "title": html_meta.get("title"),
                    "content_hash": content_hash,
                    "doc_meta": {
                        "snapshot_id": fetch_meta.get("snapshot_id"),
                        "canonical_url": html_meta.get("canonical_url") or item_url,
                        "author": html_meta.get("author"),
                        "lang": html_meta.get("lang") or profile.lang,
                        "published_at": html_meta.get("published_at"),
                        "modified_at": html_meta.get("modified_at"),
                    },
                }
            )

    if not items_to_process:
        logger.warning(
            "Extraction yielded no items for %s (Strategy: %s)",
            profile.source_id,
            profile.strategy,
        )
        return

    # 2. Trigger Document versioning & Anchor extraction (M4)
    logger.info("Extraction successful (%s items). Fanning out to organization.", len(items_to_process))
    EXTRACT_ITEMS_TOTAL.labels(
        source_id=str(profile.source_id),
        strategy=profile.strategy.value,
    ).inc(len(items_to_process))

    for item in items_to_process:
        celery.send_task(
            "app.workers.organize.run_organization",
            args=[
                profile.model_dump(),
                item["text"],
                item["content_hash"],
                item.get("url"),
                item.get("title"),
                item.get("doc_meta") or {},
            ],
            queue="organize",
        )
