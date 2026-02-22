"""Headless fetcher using Playwright — Blueprint §6.2.

Used for SPA sites where content is rendered via JavaScript.
"""
from __future__ import annotations

import logging
import asyncio
from typing import Any, Dict

from playwright.async_api import async_playwright
from app.schemas.source_profile import SourceProfile

logger = logging.getLogger(__name__)

async def fetch_headless(profile: SourceProfile, url: str) -> str:
    """Fetch SPA page using headless browser, blocking unnecessary assets."""
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        # Context with institutional User-Agent (Blueprint §6.1)
        context = await browser.new_context(
            user_agent=profile.headers.get("User-Agent", "RadarHardNews/1.0 (Institutional)")
        )
        page = await context.new_page()

        # Block assets to save bandwidth and speed up (§6.2)
        await page.route("**/*.{png,jpg,jpeg,gif,svg,css,woff,woff2,ttf,otf}", lambda route: route.abort())

        try:
            logger.info(f"Navigating to {url} (Headless)")
            await page.goto(url, wait_until="networkidle", timeout=profile.limits.timeout_seconds * 1000)
            
            # Wait for specific content if needed or just network idle
            content = await page.content()
            return content
        except Exception as e:
            logger.error(f"Headless fetch failed for {url}: {e}")
            raise
        finally:
            await browser.close()
