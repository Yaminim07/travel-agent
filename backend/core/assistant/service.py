"""Chat orchestration: route -> retrieve (structured / semantic / hybrid) -> build context -> answer.

The router and each retriever are independent and communicate only through the
plan dict, so any of them can be improved or replaced without touching the others.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from . import chain, clients, structured

logger = logging.getLogger("travel_agent.backend")

EMAIL_EXCERPT_CHARS = 3000
MAX_EMAILS = 3


def _classify(question: str) -> Dict[str, Any]:
    try:
        plan = clients.route_query(question)
        if plan.get("route") in ("STRUCTURED", "SEMANTIC", "HYBRID", "WEB"):
            return plan
        logger.error("[ASSISTANT] Router returned an invalid plan: %s", plan)
    except Exception:
        logger.exception("[ASSISTANT] Router service failed; defaulting to HYBRID.")
    return {"route": "HYBRID", "entity": "any", "time_scope": "any", "status": "any", "sort": "date_asc",
                "limit": 5, "semantic_query": question, "classified_by": "default"}


def _email_context(matches: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    emails = []
    for match in matches[:MAX_EMAILS]:
        meta = match.get("metadata", {}) or {}
        emails.append(
            {
                "subject": meta.get("subject", ""),
                "sent": meta.get("date", ""),
                "excerpt": (meta.get("body", "") or "")[:EMAIL_EXCERPT_CHARS],
            }
        )
    return emails


def _semantic(question: str, plan: Dict[str, Any], user, message_ids: Optional[List[str]] = None) -> List[Dict[str, Any]]:
    query = plan.get("semantic_query") or question
    logger.info("[ASSISTANT] Running SEMANTIC (Pinecone) search query=%r scoped_to_message_ids=%s", query, message_ids or "all")
    try:
        matches = clients.semantic_search(query, user.email, message_ids=message_ids)
        if not matches and message_ids:  # linked emails not indexed; widen to the whole mailbox
            logger.info("[ASSISTANT] No matches in linked emails; widening Pinecone search to the whole mailbox")
            matches = clients.semantic_search(query, user.email)
        logger.info("[ASSISTANT] Pinecone returned %s match(es)", len(matches))
        return matches
    except Exception:
        logger.exception("[ASSISTANT] Semantic search failed.")
        return []


def _web(question: str, plan: Dict[str, Any]) -> List[Dict[str, Any]]:
    query = plan.get("web_query") or question
    logger.info("[ASSISTANT] Running WEB search query=%r", query)
    try:
        results = clients.web_search(query)
        logger.info("[ASSISTANT] Web search returned %s result(s)", len(results))
        return results
    except Exception:
        logger.exception("[ASSISTANT] Web search failed.")
        return []


def _fallback_answer(structured_result: Dict[str, Any], emails: List[Dict[str, Any]], web: List[Dict[str, Any]]) -> str:
    """Deterministic reply used only when the answer LLM is unavailable."""
    for trip in structured_result.get("trips", [])[:1]:
        return f"Your trip: {trip['title'] or trip['location']} starting {trip['start_date']} ({trip['status']})."
    for booking in structured_result.get("bookings", [])[:1]:
        when = booking["departure_at"] or booking["check_in_at"]
        return f"{booking['type'].title()} {booking['provider']} to {booking['destination']} on {when} ({booking['status']})."
    if emails:
        return f"I found a related email: {emails[0]['subject']}."
    if web:
        return f"I found this on {web[0]['url']}: {web[0]['snippet']}"
    return "I couldn't find anything about that in your trips or emails."


def answer_question(user, question: str, today=None) -> Dict[str, Any]:
    logger.info("[ASSISTANT] Question received: %r (user=%s)", question, user.email)
    plan = _classify(question)
    route = plan["route"]
    logger.info(
        "[ASSISTANT] Intent decided: route=%s by=%s entity=%s time_scope=%s status=%s sort=%s limit=%s "
        "destination=%r provider=%r date_from=%r date_to=%r semantic_query=%r",
        route, plan.get("classified_by"), plan.get("entity"), plan.get("time_scope"), plan.get("status"),
        plan.get("sort"), plan.get("limit"), plan.get("destination"), plan.get("provider"),
        plan.get("date_from"), plan.get("date_to"), plan.get("semantic_query"),
    )
    structured_result: Dict[str, Any] = {"trips": [], "bookings": []}
    matches: List[Dict[str, Any]] = []
    web: List[Dict[str, Any]] = []

    if route in ("STRUCTURED", "HYBRID"):
        logger.info("[ASSISTANT] Running STRUCTURED (database) search")
        structured_result = structured.search(user, plan, today)
        logger.info(
            "[ASSISTANT] Database returned trips=%s bookings=%s",
            len(structured_result["trips"]), len(structured_result["bookings"]),
        )

    if route == "WEB":
        web = _web(question, plan)
    elif route == "SEMANTIC":
        matches = _semantic(question, plan, user)
    elif route == "HYBRID":
        matches = _semantic(question, plan, user, structured.message_ids(structured_result) or None)
    elif not (structured_result["trips"] or structured_result["bookings"]):
        # Structured found nothing (e.g. data not extracted); try the emails before giving up.
        route = "STRUCTURED->SEMANTIC"
        logger.info("[ASSISTANT] Database had no results; falling back to email search")
        matches = _semantic(question, plan, user)

    followup = plan.get("followup")
    if followup and route != "WEB":
        if followup["for_each"] == "provider":
            values = chain.providers(structured_result)
        else:
            values = chain.destinations(user, structured_result, matches, prefer_emails=route in ("SEMANTIC", "STRUCTURED->SEMANTIC"))
        logger.info("[ASSISTANT] Step 2 (%s) values=%s", followup["for_each"], values)
        web = chain.run_web_followup(followup, values)
    elif route in ("SEMANTIC", "HYBRID") and not matches:
        # The user's emails don't cover it (e.g. ticket omits the baggage rules); try the public web.
        logger.info("[ASSISTANT] No email matches; falling back to web search")
        web = _web(question, plan)

    emails = _email_context(matches)
    logger.info(
        "[ASSISTANT] route=%s classified_by=%s plan=%s trips=%s bookings=%s emails=%s web=%s",
        route, plan.get("classified_by"), plan, len(structured_result["trips"]), len(structured_result["bookings"]), len(emails), len(web),
    )

    try:
        answer = clients.generate_answer(question, structured_result, emails, web)
    except Exception:
        logger.exception("[ASSISTANT] Answer generation failed; using deterministic fallback.")
        answer = _fallback_answer(structured_result, emails, web)

    return {"answer": answer, "route": route, "plan": plan, "matches": matches}
