"""Headless fetcher using Playwright — Blueprint §6.2.

Used for SPA sites where content is rendered via JavaScript.
"""
from __future__ import annotations

import logging
import asyncio
from contextlib import suppress

from app.schemas.source_profile import SourceProfile

logger = logging.getLogger(__name__)

async def fetch_headless(profile: SourceProfile, url: str) -> str:
    """Fetch SPA page using headless browser, blocking unnecessary assets."""
    try:
        from playwright.async_api import async_playwright
    except Exception as exc:
        raise RuntimeError(f"Playwright unavailable for SPA_HEADLESS: {exc}") from exc

    captured_json_payloads: list[str] = []
    pending_capture_tasks: set[asyncio.Task] = set()
    md = profile.metadata if isinstance(profile.metadata, dict) else {}
    capture_cfg = md.get("headless_capture") if isinstance(md.get("headless_capture"), dict) else {}
    max_payloads = int(capture_cfg.get("max_payloads", 20) or 20)
    max_chars = int(capture_cfg.get("max_chars_per_payload", 5000) or 5000)
    url_contains = capture_cfg.get("url_contains")
    if isinstance(url_contains, str):
        url_contains = [url_contains]
    if not isinstance(url_contains, list):
        url_contains = []
    url_contains = [str(x) for x in url_contains if str(x).strip()]

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        # Context with institutional User-Agent (Blueprint §6.1)
        context = await browser.new_context(
            user_agent=profile.headers.get("User-Agent", "RadarHardNews/1.0 (Institutional)")
        )
        page = await context.new_page()

        # Block assets to save bandwidth and speed up (§6.2)
        async def _block_asset(route):
            await route.abort()

        await page.route("**/*.{png,jpg,jpeg,gif,svg,css,woff,woff2,ttf,otf}", _block_asset)

        async def _capture_response(response):
            with suppress(Exception):
                if url_contains and not any(fragment in response.url for fragment in url_contains):
                    return
                ctype = (response.headers or {}).get("content-type", "").lower()
                if "json" not in ctype:
                    return
                text = await response.text()
                text = (text or "").strip()
                if not text:
                    return
                # Keep payloads bounded to avoid blowing up queue payloads.
                if len(captured_json_payloads) < max_payloads:
                    captured_json_payloads.append(text[:max_chars])

        def _schedule_capture(response):
            task = asyncio.create_task(_capture_response(response))
            pending_capture_tasks.add(task)
            task.add_done_callback(lambda t: pending_capture_tasks.discard(t))

        page.on("response", _schedule_capture)

        try:
            logger.info(f"Navigating to {url} (Headless)")
            await page.goto(url, wait_until="networkidle", timeout=profile.limits.timeout_seconds * 1000)
            await asyncio.sleep(0.3)
            if pending_capture_tasks:
                await asyncio.gather(*list(pending_capture_tasks), return_exceptions=True)

            content = await page.content()
            if captured_json_payloads:
                # Include captured JSON/XHR payloads for extract/scoring without changing task contracts.
                xhr_blob = "\n\n".join(captured_json_payloads)
                content = f"{content}\n<!-- XHR_JSON_CAPTURE_START -->\n{xhr_blob}\n<!-- XHR_JSON_CAPTURE_END -->"
            return content
        except Exception as e:
            logger.error(f"Headless fetch failed for {url}: {e}")
            raise
        finally:
            await browser.close()
