"""LLM query router: decides how a chat question should be answered.

This module only *classifies*. It knows nothing about the database or Pinecone,
so the classification can be improved without touching either integration.
"""
from __future__ import annotations

import json
import logging
import re
from datetime import date
from typing import Any, Callable, Dict, Optional

from .prompts import ROUTER_PROMPT

logger = logging.getLogger("travel_agent.query_router")

ROUTES = ("STRUCTURED", "SEMANTIC", "HYBRID", "WEB")
ENTITIES = ("flight", "hotel", "train", "bus", "activity", "trip", "any")
TIME_SCOPES = ("upcoming", "past", "any")
STATUSES = ("confirmed", "cancelled", "any")
SORTS = ("date_asc", "date_desc", "price_asc", "price_desc")

FOLLOWUP_FOR_EACH = ("provider", "destination")

_DEFAULT_PLAN: Dict[str, Any] = {
    "route": "HYBRID",
    "entity": "any",
    "time_scope": "any",
    "status": "any",
    "date_from": "",
    "date_to": "",
    "destination": "",
    "provider": "",
    "sort": "date_asc",
    "limit": 5,
    "semantic_query": "",
    "web_query": "",
    "followup": None,
}

_ISO_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _clean_choice(value: Any, allowed: tuple, default: str) -> str:
    text = str(value or "").strip()
    for option in allowed:
        if text.lower() == option.lower():
            return option
    return default


def _clean_followup(raw: Any, route: str) -> Optional[Dict[str, str]]:
    """Optional second step: a WEB search templated on step-1 results. Never allowed on a WEB route."""
    if route == "WEB" or not isinstance(raw, dict):
        return None
    template = str(raw.get("web_template") or "").strip()[:200]
    for_each = _clean_choice(raw.get("for_each"), FOLLOWUP_FOR_EACH, "")
    if not template or not for_each or "{" + for_each + "}" not in template:
        return None
    return {"web_template": template, "for_each": for_each}


def normalize_plan(raw: Any, question: str) -> Dict[str, Any]:
    """Coerce arbitrary model output into a safe, fully-populated plan."""
    raw = raw if isinstance(raw, dict) else {}
    plan = dict(_DEFAULT_PLAN)
    plan["route"] = _clean_choice(raw.get("route"), ROUTES, "HYBRID")
    plan["entity"] = _clean_choice(raw.get("entity"), ENTITIES, "any")
    plan["time_scope"] = _clean_choice(raw.get("time_scope"), TIME_SCOPES, "any")
    plan["status"] = _clean_choice(raw.get("status"), STATUSES, "any")
    plan["sort"] = _clean_choice(raw.get("sort"), SORTS, "date_asc")
    for key in ("date_from", "date_to"):
        value = str(raw.get(key) or "").strip()
        plan[key] = value if _ISO_DATE.match(value) else ""
    for key in ("destination", "provider"):
        plan[key] = str(raw.get(key) or "").strip()[:100]
    try:
        plan["limit"] = max(1, min(int(raw.get("limit", 5)), 10))
    except (TypeError, ValueError):
        plan["limit"] = 5
    plan["semantic_query"] = str(raw.get("semantic_query") or "").strip()[:300] or question
    plan["web_query"] = str(raw.get("web_query") or "").strip()[:200] or question
    plan["followup"] = _clean_followup(raw.get("followup"), plan["route"])
    return plan


_STRUCTURED_HINTS = re.compile(
    r"\b(next|upcoming|soon|when|what time|how much|price|cost|paid|cancel+ed|status|which|how many|last|previous|past)\b", re.I
)
_SEMANTIC_HINTS = re.compile(r"\b(baggage|luggage|policy|policies|amenit\w+|breakfast|wifi|refund|check-?in time|instructions?|terminal|meal|seat)\b", re.I)
_PERSONAL_HINTS = re.compile(r"\b(my|mine|our|next|upcoming|booked|booking|ticket|reservation|trip)\b", re.I)
_WEB_HINTS = re.compile(
    r"\b(air india|indigo|vistara|emirates|lufthansa|british airways|qatar|singapore airlines|delta|united|american airlines|"
    r"airline|airport|visa|weather|currency|vaccination|customs|entry requirements?)\b", re.I
)
_ACTIVITY_HINTS = re.compile(r"\b(scuba|diving|snorkell?ing|safari|trek+ing|spa|tour|excursion|activity|concert|show)\b", re.I)
_ENTITY_HINTS = (("flight", r"\b(flight|fly|airline)\b"), ("hotel", r"\b(hotel|stay|room)\b"), ("train", r"\btrain\b"), ("bus", r"\bbus\b"), ("activity", r"\b(scuba|diving|snorkell?ing|safari|trek+ing|spa|tour|excursion|activity|activities)\b"))


def heuristic_plan(question: str) -> Dict[str, Any]:
    """Keyword fallback used when the LLM classifier is unavailable or returns junk."""
    q = question.lower()
    structured = bool(_STRUCTURED_HINTS.search(q))
    semantic = bool(_SEMANTIC_HINTS.search(q))
    if _ACTIVITY_HINTS.search(q) and _PERSONAL_HINTS.search(q):
        route = "SEMANTIC"  # activities live only in email text, not in trip/booking rows
    elif _WEB_HINTS.search(q) and not _PERSONAL_HINTS.search(q):
        route = "WEB"
    elif structured and semantic:
        route = "HYBRID"
    elif semantic:
        route = "SEMANTIC"
    elif structured:
        route = "STRUCTURED"
    else:
        route = "HYBRID"

    entity = "trip" if "trip" in q else "any"
    for name, pattern in _ENTITY_HINTS:
        if re.search(pattern, q):
            entity = name
            break

    raw: Dict[str, Any] = {"route": route, "entity": entity}
    if re.search(r"\b(next|upcoming|soon)\b", q):
        raw.update(time_scope="upcoming", sort="date_asc", limit=1 if "next" in q else 5)
    elif re.search(r"\b(last|previous|past)\b", q):
        raw.update(time_scope="past", sort="date_desc", limit=1 if re.search(r"\b(last|previous)\b", q) else 5)
    if re.search(r"\bcancel+ed\b", q):
        raw["status"] = "cancelled"
    return normalize_plan(raw, question)


def classify_query(
    question: str,
    today: date,
    llm: Optional[Callable[[str], str]] = None,
) -> Dict[str, Any]:
    """Classify ``question`` into a routing plan.

    ``llm`` takes a prompt and returns the model's JSON text. Any failure falls
    back to the keyword heuristic so chat never breaks on a bad classification.
    """
    plan: Optional[Dict[str, Any]] = None
    source = "llm"
    if llm is not None:
        try:
            text = llm(ROUTER_PROMPT.format(today=today.isoformat(), question=question))
            plan = normalize_plan(json.loads(text), question)
        except Exception:
            logger.exception("[ROUTER] LLM classification failed; using heuristic.")
    if plan is None:
        plan = heuristic_plan(question)
        source = "heuristic"
    plan["classified_by"] = source
    logger.info("[ROUTER] question=%r plan=%s", question, plan)
    return plan
