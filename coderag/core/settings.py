"""Application settings loaded from environment variables."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, Field
from dotenv import load_dotenv


load_dotenv(override=False)


def _env_str(name: str, default: Optional[str] = None) -> Optional[str]:
    """Read string value from environment with default handling."""
    value = os.getenv(name)
    if value is None or value.strip() == "":
        return default
    return value.strip()


def _env_int(name: str, default: int) -> int:
    """Read integer value from environment safely."""
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _env_bool(name: str, default: bool) -> bool:
    """Read boolean environment values using common true tokens."""
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


class Settings(BaseModel):
    """Configuration model for runtime parameters."""

    workspace_dir: Path = Field(
        default_factory=lambda: Path(_env_str("WORKSPACE_DIR", "workspace"))
    )
    data_dir: Path = Field(
        default_factory=lambda: Path(_env_str("DATA_DIR", "storage"))
    )
    max_context_chars: int = Field(
        default_factory=lambda: _env_int("MAX_CONTEXT_CHARS", 16000)
    )
    graph_hops: int = Field(default_factory=lambda: _env_int("GRAPH_HOPS", 2))
    retrieval_top_n: int = Field(
        default_factory=lambda: _env_int("RETRIEVAL_TOP_N", 60)
    )
    rerank_top_k: int = Field(
        default_factory=lambda: _env_int("RERANK_TOP_K", 15)
    )
    embedding_size: int = Field(
        default_factory=lambda: _env_int("EMBEDDING_SIZE", 256)
    )

    llm_provider: str = Field(
        default_factory=lambda: _env_str("LLM_PROVIDER", "local") or "local"
    )
    openai_api_key: Optional[str] = Field(
        default_factory=lambda: _env_str("OPENAI_API_KEY")
    )
    openai_base_url: str = Field(
        default_factory=lambda: (
            _env_str("OPENAI_BASE_URL", "https://api.openai.com/v1")
            or "https://api.openai.com/v1"
        )
    )
    openai_answer_model: str = Field(
        default_factory=lambda: (
            _env_str("OPENAI_ANSWER_MODEL", "gpt-4.1-mini")
            or "gpt-4.1-mini"
        )
    )

    gemini_api_key: Optional[str] = Field(
        default_factory=lambda: _env_str("GEMINI_API_KEY")
    )
    gemini_answer_model: str = Field(
        default_factory=lambda: (
            _env_str("GEMINI_ANSWER_MODEL", "gemini-2.0-flash")
            or "gemini-2.0-flash"
        )
    )

    vertex_ai_api_key: Optional[str] = Field(
        default_factory=lambda: _env_str("VERTEX_AI_API_KEY")
    )
    vertex_project_id: Optional[str] = Field(
        default_factory=lambda: _env_str("VERTEX_PROJECT_ID")
    )
    vertex_location: str = Field(
        default_factory=lambda: (
            _env_str("VERTEX_LOCATION", "us-central1")
            or "us-central1"
        )
    )
    vertex_answer_model: str = Field(
        default_factory=lambda: (
            _env_str("VERTEX_ANSWER_MODEL", "gemini-2.0-flash")
            or "gemini-2.0-flash"
        )
    )

    use_neo4j: bool = Field(
        default_factory=lambda: _env_bool("USE_NEO4J", False)
    )
    neo4j_uri: Optional[str] = Field(
        default_factory=lambda: _env_str("NEO4J_URI")
    )
    neo4j_user: Optional[str] = Field(
        default_factory=lambda: _env_str("NEO4J_USER")
    )
    neo4j_password: Optional[str] = Field(
        default_factory=lambda: _env_str("NEO4J_PASSWORD")
    )

    use_rq: bool = Field(default_factory=lambda: _env_bool("USE_RQ", False))
    redis_url: str = Field(
        default_factory=lambda: (
            _env_str("REDIS_URL", "redis://localhost:6379/0")
            or "redis://localhost:6379/0"
        )
    )

    def resolve_llm_provider(self, override: Optional[str] = None) -> str:
        """Resolve effective provider considering request override."""
        return (override or self.llm_provider).strip().lower()

    def is_provider_configured(self, provider: str) -> bool:
        """Check whether provider credentials are available."""
        provider_name = provider.strip().lower()
        if provider_name == "openai":
            return bool(self.openai_api_key)
        if provider_name == "gemini":
            return bool(self.gemini_api_key)
        if provider_name == "vertex_ai":
            return bool(self.vertex_ai_api_key and self.vertex_project_id)
        return True


SETTINGS = Settings()
