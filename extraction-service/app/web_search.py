"""Tavily web search client. Returns [] on any failure so chat never breaks on search."""
from __future__ import annotations

import logging
from typing import Dict, List

import httpx

from .config import get_settings

logger = logging.getLogger("travel_agent.web_search")

SEARCH_URL = "https://api.tavily.com/search"
MAX_RESULTS = 10
SNIPPET_CHARS = 1500


def web_search(query: str, num: int = 5) -> List[Dict[str, str]]:
    settings = get_settings()
    if not settings.tavily_api_key:
        logger.error("[WEB] TAVILY_API_KEY not configured.")
        return []
    try:
        response = httpx.post(
            SEARCH_URL,
            headers={"Authorization": f"Bearer {settings.tavily_api_key}"},
            json={"query": query, "max_results": max(1, min(num, MAX_RESULTS)), "search_depth": "basic", "include_answer": False},
            timeout=settings.web_search_timeout,
        )
        response.raise_for_status()
        items = response.json().get("results", [])
    except Exception as exc:
        logger.error("[WEB] Tavily search failed: %s", type(exc).__name__)
        return []
    results = [
        {"title": item.get("title", ""), "url": item.get("url", ""), "snippet": " ".join((item.get("content") or "").split())[:SNIPPET_CHARS]}
        for item in items
    ]
    logger.info("[WEB] query=%r results=%s", query, len(results))
    return results
