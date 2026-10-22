"""Second retrieval step: a web search templated on what the first step found.

Inputs come only from the user's own rows/emails, never from raw model text, so the
LLM plan only supplies the query template.
"""
from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Dict, List

from core.models import Booking

from . import clients

logger = logging.getLogger("travel_agent.backend")

MAX_FANOUT = 4  # distinct values searched per question (Tavily cost / latency cap)


def _distinct(values) -> List[str]:
    return list(dict.fromkeys(v.strip() for v in values if v and v.strip()))


def _bookings(structured_result: Dict[str, Any]) -> List[Dict[str, Any]]:
    rows = list(structured_result.get("bookings", []))
    for trip in structured_result.get("trips", []):
        rows.extend(trip.get("bookings", []))
    return rows


def providers(structured_result: Dict[str, Any]) -> List[str]:
    return _distinct(b.get("provider") for b in _bookings(structured_result))


def _email_destinations(user, matches: List[Dict[str, Any]]) -> List[str]:
    """Place(s) for the best-matching email: the DB booking behind it, else an LLM read of the email text."""
    metas = [m.get("metadata", {}) or {} for m in matches[:MAX_FANOUT]]
    if not metas:
        return []
    ids = [m.get("message_id") for m in metas if m.get("message_id")]
    rows = Booking.objects.filter(trip__user=user, gmail_message_id__in=ids).select_related("trip")
    found = _distinct([b.destination or b.trip.location for b in rows])
    if found:
        return found
    try:
        return _distinct([clients.extract_destination(metas[0].get("subject", ""), metas[0].get("body", ""))])
    except Exception:
        logger.exception("[ASSISTANT] Destination extraction failed.")
        return []


def destinations(user, structured_result: Dict[str, Any], matches: List[Dict[str, Any]], prefer_emails: bool = False) -> List[str]:
    """Places from step 1. When step 1 was an email search, the email wins; otherwise structured rows come first."""
    structured_found = _distinct(
        [b.get("destination") for b in _bookings(structured_result)]
        + [t.get("location") for t in structured_result.get("trips", [])]
    )
    if prefer_emails:
        return _email_destinations(user, matches) or structured_found
    return structured_found or _email_destinations(user, matches)


def run_web_followup(followup: Dict[str, str], values: List[str]) -> List[Dict[str, Any]]:
    """One Tavily search per value (in parallel). Each result is tagged with the value it was searched for."""
    values = values[:MAX_FANOUT]
    queries = [followup["web_template"].replace("{" + followup["for_each"] + "}", v) for v in values]

    def search(query: str) -> List[Dict[str, Any]]:
        try:
            return clients.web_search(query, num=3)
        except Exception:
            logger.exception("[ASSISTANT] Follow-up web search failed for %r.", query)
            return []

    logger.info("[ASSISTANT] Follow-up WEB searches: %s", queries)
    if not queries:
        return []
    with ThreadPoolExecutor(max_workers=len(queries)) as pool:
        batches = list(pool.map(search, queries))
    return [{"for": value, **result} for value, batch in zip(values, batches) for result in batch]
