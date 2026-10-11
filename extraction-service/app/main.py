from __future__ import annotations

import json
from typing import Any

from fastapi import FastAPI, HTTPException
from pydantic import ValidationError

from .config import get_settings
from .context import SYSTEM_CONTEXT
from .models import ExtractionInput, ExtractionResult

try:
    import google.generativeai as genai
except Exception:  # pragma: no cover - optional dependency path
    genai = None

try:
    from openai import OpenAI
except Exception:  # pragma: no cover - optional dependency path
    OpenAI = None

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
    if not payload.messages:
        raise HTTPException(status_code=400, detail="No messages were provided for extraction.")

    settings = get_settings()
    provider = settings.llm_provider

    if provider == "gemini":
        if not settings.gemini_api_key:
            raise HTTPException(status_code=500, detail="GEMINI_API_KEY is not configured.")
        if genai is None:
            raise HTTPException(status_code=500, detail="google-generativeai is not installed.")
    else:
        if not settings.openai_api_key:
            raise HTTPException(status_code=500, detail="OPENAI_API_KEY is not configured.")
        if OpenAI is None:
            raise HTTPException(status_code=500, detail="openai package is not installed.")

    try:
        prompt = (
            SYSTEM_CONTEXT
            + "\n\nReturn only valid JSON with this structure: "
            + '{"trips": [{"title": "", "location": "", "start_date": "", "end_date": "", "status": "upcoming"}], "bookings": [{"booking_type": "flight", "provider_name": "", "confirmation_number": "", "origin": "", "destination": "", "departure_at": "", "arrival_at": "", "check_in_at": "", "check_out_at": "", "currency": "USD", "total_amount": 0.0, "status": "confirmed", "confidence_score": 0.0}], "notes": ""}'
        )
        request_payload = json.dumps(payload.model_dump(mode="json", by_alias=True, exclude_none=True), ensure_ascii=False)

        if provider == "gemini":
            genai.configure(api_key=settings.gemini_api_key)
            model = genai.GenerativeModel(settings.gemini_model)
            response = model.generate_content(
                [
                    {"text": prompt},
                    {"text": request_payload},
                ],
                generation_config={"response_mime_type": "application/json"},
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

        if not content:
            raise HTTPException(status_code=502, detail=f"{provider.title()} returned an empty response.")

        parsed = json.loads(content)
        result = ExtractionResult.model_validate(parsed)
        return result
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=502, detail=f"{provider.title()} response was not valid JSON: {str(exc)}") from exc
    except ValidationError as exc:
        raise HTTPException(status_code=502, detail=f"{provider.title()} output did not match the expected schema: {str(exc)}") from exc
    except Exception as exc:  # pragma: no cover - external API error path
        raise HTTPException(status_code=502, detail=f"Extraction failed: {str(exc)}") from exc
