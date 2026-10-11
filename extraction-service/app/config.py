from __future__ import annotations

import os
from functools import lru_cache

from dotenv import load_dotenv
from pydantic import BaseModel

load_dotenv()


class Settings(BaseModel):
    app_env: str = os.getenv("APP_ENV", "development")
    service_port: int = int(os.getenv("SERVICE_PORT", "8001"))
    llm_provider: str = os.getenv("LLM_PROVIDER", "gemini").lower()
    openai_api_key: str = os.getenv("OPENAI_API_KEY", "")
    openai_model: str = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
    gemini_api_key: str = os.getenv("GEMINI_API_KEY", "")
    gemini_model: str = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")
    gemini_embedding_model: str = os.getenv("GEMINI_EMBEDDING_MODEL", "text-embedding-004")
    pinecone_api_key: str = os.getenv("PINECONE_API_KEY", "")
    pinecone_environment: str = os.getenv("PINECONE_ENVIRONMENT", "us-east-1-aws")
    pinecone_index_name: str = os.getenv("PINECONE_INDEX_NAME", "")
    pinecone_namespace: str = os.getenv("PINECONE_NAMESPACE", "travel-agent")
    pinecone_vector_dimension: int = int(os.getenv("PINECONE_VECTOR_DIMENSION", "768"))


@lru_cache
def get_settings() -> Settings:
    return Settings()
