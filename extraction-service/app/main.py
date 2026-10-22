from __future__ import annotations

import json
import logging
from datetime import date
from typing import Any

from fastapi import FastAPI, HTTPException
from pydantic import ValidationError

from .config import get_settings
from .models import ExtractionInput, ExtractionResult
from .schema import TRAVEL_EXTRACTION_SCHEMA
from .prompts import ANSWER_PROMPT, DESTINATION_PROMPT, SYSTEM_CONTEXT
from .query_router import classify_query
from .web_search import web_search
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


def _generate_text(prompt: str, json_mode: bool = False) -> str:
    """Single-prompt completion on the configured provider. Raises on any failure."""
    settings = get_settings()
    if settings.llm_provider == "gemini":
        if not settings.gemini_api_key or genai is None:
            raise RuntimeError("Gemini is not configured.")
        genai.configure(api_key=settings.gemini_api_key)
        model = genai.GenerativeModel(settings.gemini_model)
        config = {"temperature": 0.1}
        if json_mode:
            config["response_mime_type"] = "application/json"
        text = model.generate_content(prompt, generation_config=config).text
    else:
        if not settings.openai_api_key or OpenAI is None:
            raise RuntimeError("OpenAI is not configured.")
        kwargs: dict[str, Any] = {"response_format": {"type": "json_object"}} if json_mode else {}
        completion = OpenAI(api_key=settings.openai_api_key).chat.completions.create(
            model=settings.openai_model,
            temperature=0.1,
            messages=[{"role": "user", "content": prompt}],
            **kwargs,
        )
        text = completion.choices[0].message.content
    if not text or not str(text).strip():
        raise RuntimeError("Model returned an empty response.")
    return str(text).strip()


@app.post("/route")
def route(query: dict[str, Any]) -> dict[str, Any]:
    question = str((query or {}).get("query", "")).strip()
    if not question:
        raise HTTPException(status_code=400, detail="A search query is required.")
    return classify_query(question, date.today(), llm=lambda prompt: _generate_text(prompt, json_mode=True))


@app.post("/semantic-search")
def semantic_search(query: dict[str, Any]) -> dict[str, Any]:
    question = str((query or {}).get("query", "")).strip()
    user_email = str((query or {}).get("user_email", "")).strip()
    if not question or not user_email:
        raise HTTPException(status_code=400, detail="query and user_email are required.")

    message_ids = [str(i) for i in (query.get("message_ids") or []) if i]
    top_k = max(1, min(int(query.get("top_k") or 5), 10))
    matches = search_relevant_travel_documents(question, top_k=top_k, user_email=user_email, message_ids=message_ids or None)
    logger.info("[SEMANTIC] query=%r message_ids=%s matches=%s", question, len(message_ids), len(matches))
    return {"matches": matches, "match_count": len(matches)}


@app.post("/web-search")
def web_search_endpoint(query: dict[str, Any]) -> dict[str, Any]:
    question = str((query or {}).get("query", "")).strip()
    if not question:
        raise HTTPException(status_code=400, detail="A search query is required.")
    results = web_search(question, num=int(query.get("num") or 5))
    return {"results": results, "result_count": len(results)}


@app.post("/extract-destination")
def extract_destination(payload: dict[str, Any]) -> dict[str, Any]:
    body = str((payload or {}).get("body", "")).strip()
    if not body:
        raise HTTPException(status_code=400, detail="An email body is required.")
    prompt = DESTINATION_PROMPT.format(subject=str(payload.get("subject", ""))[:300], body=body[:3000])
    try:
        destination = str(json.loads(_generate_text(prompt, json_mode=True)).get("destination") or "").strip()
    except Exception as exc:
        logger.exception("[DESTINATION] Extraction failed.")
        raise HTTPException(status_code=502, detail=f"Destination extraction failed: {str(exc)}") from exc
    return {"destination": destination[:100]}


@app.post("/answer")
def answer(payload: dict[str, Any]) -> dict[str, Any]:
    question = str((payload or {}).get("question", "")).strip()
    if not question:
        raise HTTPException(status_code=400, detail="A question is required.")

    prompt = ANSWER_PROMPT.format(
        today=date.today().isoformat(),
        question=question,
        structured=json.dumps(payload.get("structured") or {}, ensure_ascii=False, default=str),
        emails=json.dumps(payload.get("emails") or [], ensure_ascii=False, default=str),
        web=json.dumps(payload.get("web") or [], ensure_ascii=False, default=str),
    )
    try:
        return {"answer": _generate_text(prompt)}
    except Exception as exc:
        logger.exception("[ANSWER] Generation failed.")
        raise HTTPException(status_code=502, detail=f"Answer generation failed: {str(exc)}") from exc


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

    indexed = upsert_relevant_travel_documents(extraction_result, messages, str(payload.get("user_email", "")))
    logger.info("[INDEX] Pinecone indexing result=%s", indexed)
    return {
        "status": "ok",
        "indexed": indexed,
    }
