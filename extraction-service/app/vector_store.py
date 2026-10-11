from __future__ import annotations

import hashlib
import json
import logging
from typing import Any, Dict, List, Optional

from .config import get_settings
from .models import ExtractionResult

logger = logging.getLogger("travel_agent.vector_store")

try:
    from pinecone import Pinecone
except Exception:  # pragma: no cover - optional dependency path
    Pinecone = None

try:
    import google.generativeai as genai
except Exception:  # pragma: no cover - optional dependency path
    genai = None


def _stable_float_vector(text: str, vector_size: Optional[int] = None) -> List[float]:
    """Deterministic placeholder embedding for local/dev usage before Pinecone is configured.

    Matches the configured Pinecone index dimension so the placeholder vectors remain valid.
    """
    if vector_size is None:
        vector_size = get_settings().pinecone_vector_dimension

    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
    values: List[float] = []
    for i in range(vector_size):
        start = (i * 2) % len(digest)
        end = (i * 2 + 2) % len(digest)
        if end == 0:
            end = len(digest)
        byte_val = int(digest[start:end], 16)
        values.append((byte_val / 255.0) * 2.0 - 1.0)
    return values


def _gemini_embedding(text: str, task_type: str) -> Optional[List[float]]:
    """Generate a real embedding for ``text`` using the Gemini embedding model.

    ``task_type`` should be ``"retrieval_document"`` for content being indexed and
    ``"retrieval_query"`` for search queries so the vectors live in the same
    retrieval space. Returns ``None`` when embeddings are not configured, the
    library is missing, or the request fails so the caller can fall back to the
    deterministic placeholder vector and keep indexing/search working locally.
    """
    settings = get_settings()
    if genai is None:
        logger.warning("[EMBED] google-generativeai library is not installed; using placeholder embedding.")
        return None
    if not settings.gemini_api_key:
        logger.warning("[EMBED] GEMINI_API_KEY is not set; using placeholder embedding.")
        return None

    model_name = settings.gemini_embedding_model
    expected_dim = settings.pinecone_vector_dimension

    # Try progressively simpler request shapes so we keep working across
    # embedding-model / SDK variants that reject output_dimensionality or task_type.
    attempts = (
        {"task_type": task_type, "output_dimensionality": expected_dim},
        {"task_type": task_type},
        {},
    )
    for extra in attempts:
        try:
            genai.configure(api_key=settings.gemini_api_key)
            result = genai.embed_content(model=model_name, content=text, **extra)
        except Exception:
            logger.warning(
                "[EMBED] embed_content attempt failed for model=%s params=%s.",
                model_name,
                list(extra.keys()) or ["<none>"],
                exc_info=True,
            )
            continue

        embedding = result.get("embedding") if isinstance(result, dict) else getattr(result, "embedding", None)
        if not embedding:
            logger.warning("[EMBED] Gemini returned an empty embedding for model=%s.", model_name)
            continue

        values = [float(v) for v in embedding]
        if len(values) != expected_dim:
            logger.warning(
                "[EMBED] Embedding dimension mismatch: got %s, expected %s for model=%s.",
                len(values),
                expected_dim,
                model_name,
            )
            continue
        return values

    logger.error(
        "[EMBED] All Gemini embedding attempts failed for model=%s task_type=%s; using placeholder embedding.",
        model_name,
        task_type,
    )
    return None


def _embed_text(text: str, task_type: str = "retrieval_document") -> List[float]:
    """Return a real Gemini embedding when available, otherwise a placeholder vector.

    This preserves graceful degradation for local/dev setups where embeddings are
    not configured, while producing genuine semantic vectors whenever possible.
    """
    embedding = _gemini_embedding(text, task_type=task_type)
    if embedding is not None:
        return embedding

    logger.info("[EMBED] Using placeholder embedding for text (%s chars).", len(text or ""))
    return _stable_float_vector(text)


def _build_relevant_document(message: Dict[str, Any], extraction_result: ExtractionResult) -> Optional[Dict[str, Any]]:
    if not extraction_result.trips and not extraction_result.bookings:
        return None

    raw_text = (message.get("body") or "")
    if not raw_text.strip():
        return None

    body_text = raw_text[:20000]
    payload = {
        "id": str(message.get("id") or hashlib.sha256(json.dumps(message, sort_keys=True).encode("utf-8")).hexdigest()),
        "text": raw_text,
        "metadata": {
            "message_id": message.get("id", ""),
            "thread_id": message.get("threadId", ""),
            "subject": message.get("subject", ""),
            "from": message.get("from_email", ""),
            "date": message.get("date", ""),
            "trip_count": len(extraction_result.trips),
            "booking_count": len(extraction_result.bookings),
            "travel_status": extraction_result.trips[0].status if extraction_result.trips else "unknown",
            "body": body_text,
        },
    }
    payload["values"] = _embed_text(payload["text"], task_type="retrieval_document")
    return payload


def is_pinecone_configured() -> bool:
    settings = get_settings()
    configured = bool(settings.pinecone_api_key and settings.pinecone_index_name)
    logger.info("[PINECONE] Configured=%s index_name_set=%s namespace=%s", configured, bool(settings.pinecone_index_name), settings.pinecone_namespace)
    return configured


def get_pinecone_index():
    if not is_pinecone_configured():
        return None

    if Pinecone is None:
        raise RuntimeError("pinecone package is not installed.")

    settings = get_settings()
    client = Pinecone(api_key=settings.pinecone_api_key)
    return client.Index(settings.pinecone_index_name)


def upsert_relevant_travel_documents(extraction_result: ExtractionResult, raw_messages: List[Dict[str, Any]]) -> Dict[str, Any]:
    logger.info("[PINECONE] Attempting to index %s message(s) for extraction result with %s trip(s) and %s booking(s)", len(raw_messages), len(extraction_result.trips), len(extraction_result.bookings))
    if not extraction_result.trips and not extraction_result.bookings:
        logger.warning("[PINECONE] No extracted trip or booking data present; skipping Pinecone write.")
        return {
            "status": "skipped",
            "indexed_count": 0,
            "reason": "No extracted trip or booking data was produced for the current batch.",
        }

    documents = []
    for message in raw_messages:
        document = _build_relevant_document(message, extraction_result)
        if document:
            documents.append(document)

    logger.info("[PINECONE] Built %s candidate document(s) from raw messages.", len(documents))

    if not documents:
        logger.warning("[PINECONE] No eligible message bodies were built into documents.")
        return {
            "status": "skipped",
            "indexed_count": 0,
            "reason": "No raw message content was eligible for Pinecone indexing after extraction.",
        }

    if not is_pinecone_configured():
        logger.warning("[PINECONE] Pinecone settings are missing or incomplete.")
        return {
            "status": "not_configured",
            "indexed_count": len(documents),
            "reason": "Pinecone is not configured yet. The relevant docs are ready to index once the environment variables are set.",
        }

    try:
        logger.info("[PINECONE] Connecting to Pinecone index=%s namespace=%s", get_settings().pinecone_index_name, get_settings().pinecone_namespace)
        index = get_pinecone_index()
        if index is None:
            raise RuntimeError("Pinecone index was not created.")

        vectors = [{"id": doc["id"], "values": doc["values"], "metadata": doc["metadata"]} for doc in documents]
        index.upsert(vectors=vectors, namespace=get_settings().pinecone_namespace)
        logger.info("[PINECONE] Successful upsert for %s vector(s).", len(vectors))
        return {
            "status": "indexed",
            "indexed_count": len(documents),
            "namespace": get_settings().pinecone_namespace,
        }
    except Exception as exc:  # pragma: no cover - external service path
        logger.exception("[PINECONE] Upsert failed: %s", exc)
        return {
            "status": "error",
            "indexed_count": 0,
            "reason": str(exc),
        }


def search_relevant_travel_documents(query: str, top_k: int = 5) -> List[Dict[str, Any]]:
    if not query or not query.strip():
        return []

    if not is_pinecone_configured():
        return []

    try:
        index = get_pinecone_index()
        if index is None:
            return []

        vector = _embed_text(query.strip(), task_type="retrieval_query")
        results = index.query(
            vector=vector,
            top_k=top_k,
            include_metadata=True,
            namespace=get_settings().pinecone_namespace,
        )

        if isinstance(results, dict):
            matches = results.get("matches", [])
        else:
            matches = getattr(results, "matches", []) or []

        normalized_matches: List[Dict[str, Any]] = []
        for item in matches:
            item_dict = item if isinstance(item, dict) else getattr(item, "to_dict", lambda: item.__dict__)()
            if not isinstance(item_dict, dict):
                continue

            metadata = item_dict.get("metadata", {}) if isinstance(item_dict.get("metadata", {}), dict) else getattr(item, "metadata", {})
            normalized_matches.append(
                {
                    "id": item_dict.get("id", getattr(item, "id", None)),
                    "score": item_dict.get("score", getattr(item, "score", 0.0)),
                    "metadata": metadata,
                }
            )

        return normalized_matches
    except Exception:  # pragma: no cover - external service path
        return []
