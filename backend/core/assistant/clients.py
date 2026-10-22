"""HTTP clients for the extraction service's LLM and Pinecone endpoints."""
from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional

import requests
from django.conf import settings
from django.core.serializers.json import DjangoJSONEncoder

logger = logging.getLogger("travel_agent.backend")


def _post(path: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    response = requests.post(
        f"{settings.EXTRACTION_SERVICE_URL.rstrip('/')}{path}",
        json=json.loads(json.dumps(payload, cls=DjangoJSONEncoder)),  # dates/datetimes/Decimals from the ORM
        timeout=getattr(settings, "EXTRACTION_SERVICE_TIMEOUT", 120),
    )
    response.raise_for_status()
    return response.json()


def route_query(question: str) -> Dict[str, Any]:
    return _post("/route", {"query": question})


def semantic_search(
    question: str, user_email: str, message_ids: Optional[List[str]] = None, top_k: int = 5
) -> List[Dict[str, Any]]:
    payload = {"query": question, "user_email": user_email, "top_k": top_k, "message_ids": message_ids or []}
    return _post("/semantic-search", payload).get("matches", [])


def web_search(query: str, num: int = 5) -> List[Dict[str, Any]]:
    return _post("/web-search", {"query": query, "num": num}).get("results", [])


def extract_destination(subject: str, body: str) -> str:
    return _post("/extract-destination", {"subject": subject, "body": body}).get("destination", "")


def generate_answer(
    question: str, structured: Dict[str, Any], emails: List[Dict[str, Any]], web: Optional[List[Dict[str, Any]]] = None
) -> str:
    return _post("/answer", {"question": question, "structured": structured, "emails": emails, "web": web or []})["answer"]
