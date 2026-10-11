from __future__ import annotations

import json
import logging
from typing import Any

from fastapi import FastAPI, HTTPException
from pydantic import ValidationError

from .config import get_settings
from .context import SYSTEM_CONTEXT
from .models import ExtractionInput, ExtractionResult
from .schema import TRAVEL_EXTRACTION_SCHEMA
from .search_prompt import SEARCH_PROMPT
from .vector_store import search_relevant_travel_documents, upsert_relevant_travel_documents

try:
    import google.generativeai as genai
except Exception:  # pragma: no cover - optional dependency path
    genai = None

try:
    from openai import OpenAI
except Exception:  # pragma: no cover - optional dependency path
    OpenAI = None

logger = logging.getLogger("travel_agent.extraction_service")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

app = FastAPI(title="Travel Agent Extraction Service", version="0.1.0")


@app.get("/health")
def health() -> dict[str, Any]:
    settings = get_settings()
    provider = settings.llm_provider
    if provider == "gemini":
        api_key_configured = bool(settings.gemini_api_key)
        model_name = settings.gemini_model
    else:
        api_key_configured = bool(settings.openai_api_key)
        model_name = settings.openai_model

    return {
        "status": "ok",
        "app_env": settings.app_env,
        "service_port": settings.service_port,
        "provider": provider,
        "model": model_name,
        "api_key_configured": api_key_configured,
    }


@app.post("/extract", response_model=ExtractionResult)
def extract(payload: ExtractionInput) -> ExtractionResult:
    logger.info("[EXTRACT] Received %s message(s) for user %s", len(payload.messages), payload.user_email)
    if not payload.messages:
        logger.warning("[EXTRACT] No messages provided in extraction payload.")
        raise HTTPException(status_code=400, detail="No messages were provided for extraction.")

    settings = get_settings()
    provider = settings.llm_provider
    logger.info("[EXTRACT] Configured provider=%s model=%s", provider, settings.gemini_model if provider == "gemini" else settings.openai_model)

    if provider == "gemini":
        if not settings.gemini_api_key:
            logger.error("[EXTRACT] GEMINI_API_KEY missing.")
            raise HTTPException(status_code=500, detail="GEMINI_API_KEY is not configured.")
        if genai is None:
            logger.error("[EXTRACT] google-generativeai library missing.")
            raise HTTPException(status_code=500, detail="google-generativeai is not installed.")
    else:
        if not settings.openai_api_key:
            logger.error("[EXTRACT] OPENAI_API_KEY missing.")
            raise HTTPException(status_code=500, detail="OPENAI_API_KEY is not configured.")
        if OpenAI is None:
            logger.error("[EXTRACT] openai library missing.")
            raise HTTPException(status_code=500, detail="openai package is not installed.")

    try:
        response_schema = TRAVEL_EXTRACTION_SCHEMA
        prompt = (
            SYSTEM_CONTEXT
            + "\n\nReturn only valid JSON that matches this schema exactly. Do not add any extra fields. "
            + json.dumps(response_schema, ensure_ascii=False)
        )
        request_payload = json.dumps(payload.model_dump(mode="json", by_alias=True, exclude_none=True), ensure_ascii=False)
        logger.info("[EXTRACT] Sending prompt and message payload to model.")

        if provider == "gemini":
            genai.configure(api_key=settings.gemini_api_key)
            model = genai.GenerativeModel(settings.gemini_model)
            response = model.generate_content(
                [
                    {"text": prompt},
                    {"text": request_payload},
                ],
                generation_config={
                    "response_mime_type": "application/json",
                    "response_schema": response_schema,
                },
            )
            content = response.text
        else:
            client = OpenAI(api_key=settings.openai_api_key)
            completion = client.chat.completions.create(
                model=settings.openai_model,
                temperature=0.1,
                response_format={"type": "json_object"},
                messages=[
                    {"role": "system", "content": prompt},
                    {"role": "user", "content": request_payload},
                ],
            )
            content = completion.choices[0].message.content

        logger.info("[EXTRACT] Model returned content length=%s", len(content or ""))
        if not content:
            logger.error("[EXTRACT] Model returned empty content.")
            raise HTTPException(status_code=502, detail=f"{provider.title()} returned an empty response.")

        parsed = json.loads(content)
        logger.info("[EXTRACT] Parsed extraction JSON successfully. Keys=%s", list(parsed.keys()) if isinstance(parsed, dict) else type(parsed).__name__)
        result = ExtractionResult.model_validate(parsed)
        logger.info("[EXTRACT] Validation succeeded. Trips=%s Bookings=%s", len(result.trips), len(result.bookings))
        return result
    except json.JSONDecodeError as exc:
        logger.exception("[EXTRACT] JSON decode failed: %s", exc)
        raise HTTPException(status_code=502, detail=f"{provider.title()} response was not valid JSON: {str(exc)}") from exc
    except ValidationError as exc:
        logger.exception("[EXTRACT] Validation failed: %s", exc)
        raise HTTPException(status_code=502, detail=f"{provider.title()} output did not match the expected schema: {str(exc)}") from exc
    except Exception as exc:  # pragma: no cover - external API error path
        logger.exception("[EXTRACT] Extraction failed: %s", exc)
        raise HTTPException(status_code=502, detail=f"Extraction failed: {str(exc)}") from exc


def _build_search_answer(question: str, matches: list[dict[str, Any]]) -> str:
    if not matches:
        return f"I couldn’t find a matching travel record for: {question}. Try asking about a specific airline, hotel, or trip name."

    top_match = matches[0]
    metadata = top_match.get("metadata", {}) or {}
    subject = metadata.get("subject") or "your travel booking"
    message_date = metadata.get("date") or "an unknown date"
    travel_status = metadata.get("travel_status") or "confirmed"
    trip_count = metadata.get("trip_count")
    booking_count = metadata.get("booking_count")

    intro = f"I found a likely match for that: {subject}."
    context = f"It was recorded on {message_date} and looks {travel_status}."

    if trip_count is not None or booking_count is not None:
        summary = (
            f"This record references {trip_count if trip_count is not None else 0} trip(s) "
            f"and {booking_count if booking_count is not None else 0} booking(s)."
        )
    else:
        summary = "It looks like a relevant travel reminder from your inbox."

    if len(matches) > 1:
        follow_up = f"I also found {len(matches) - 1} related travel records you might want to review."
        return f"{intro} {context} {summary} {follow_up}"

    return f"{intro} {context} {summary}"


def _generate_gemini_search_answer(question: str, matches: list[dict[str, Any]]) -> str:
    settings = get_settings()
    if settings.llm_provider != "gemini":
        return _build_search_answer(question, matches)
    if not settings.gemini_api_key or genai is None:
        return _build_search_answer(question, matches)

    try:
        genai.configure(api_key=settings.gemini_api_key)
        model = genai.GenerativeModel(settings.gemini_model)
        evidence = json.dumps(matches[:5], ensure_ascii=False)
        prompt = SEARCH_PROMPT.format(question=question, evidence=evidence)
        response = model.generate_content(prompt)
        answer = getattr(response, "text", None)
        if answer and str(answer).strip():
            return str(answer).strip()
    except Exception:
        logger.exception("[SEARCH] Gemini answer generation failed; falling back to metadata summary.")

    return _build_search_answer(question, matches)


@app.post("/search")
def search(query: dict[str, Any]) -> dict[str, Any]:
    question = str((query or {}).get("query", "")).strip()
    if not question:
        raise HTTPException(status_code=400, detail="A search query is required.")

    matches = search_relevant_travel_documents(question, top_k=5)
    answer = _generate_gemini_search_answer(question, matches)
    return {
        "answer": answer,
        "matches": matches,
        "match_count": len(matches),
    }


@app.post("/index-relevant-messages")
def index_relevant_messages(payload: dict[str, Any]) -> dict[str, Any]:
    messages = payload.get("messages", [])
    result = payload.get("result")
    logger.info("[INDEX] Received %s message(s) for Pinecone indexing.", len(messages))

    if not messages:
        logger.warning("[INDEX] No messages supplied for indexing.")
        raise HTTPException(status_code=400, detail="Messages are required for indexing.")

    try:
        extraction_result = ExtractionResult.model_validate(result or {"trips": [], "bookings": [], "notes": ""})
        logger.info("[INDEX] Extraction payload validated. Trips=%s Bookings=%s", len(extraction_result.trips), len(extraction_result.bookings))
    except ValidationError as exc:
        logger.exception("[INDEX] Invalid extraction payload: %s", exc)
        raise HTTPException(status_code=400, detail=f"Invalid extraction payload: {str(exc)}") from exc

    indexed = upsert_relevant_travel_documents(extraction_result, messages)
    logger.info("[INDEX] Pinecone indexing result=%s", indexed)
    return {
        "status": "ok",
        "indexed": indexed,
    }
