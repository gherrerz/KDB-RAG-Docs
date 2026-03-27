"""Application settings loaded from environment variables."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, Field, field_validator, model_validator
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


REPO_ROOT = Path(__file__).resolve().parents[3]


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
    ingest_embedding_workers: int = Field(
        default_factory=lambda: _env_int("INGEST_EMBED_WORKERS", 4)
    )
    chroma_upsert_batch_size: int = Field(
        default_factory=lambda: _env_int("CHROMA_UPSERT_BATCH_SIZE", 128)
    )
    use_chroma: bool = Field(
        default_factory=lambda: _env_bool("USE_CHROMA", True)
    )
    chroma_persist_dir: Path = Field(
        default_factory=lambda: Path(
            _env_str("CHROMA_PERSIST_DIR", "storage/chromadb")
            or "storage/chromadb"
        )
    )
    chroma_collection: str = Field(
        default_factory=lambda: (
            _env_str("CHROMA_COLLECTION", "coderag_chunks")
            or "coderag_chunks"
        )
    )

    llm_provider: str = Field(
        default_factory=lambda: _env_str("LLM_PROVIDER", "local") or "local"
    )
    llm_embedding: Optional[str] = Field(
        default_factory=lambda: _env_str("LLM_EMBEDDING")
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
    openai_embedding_model: str = Field(
        default_factory=lambda: (
            _env_str("OPENAI_EMBEDDING_MODEL", "text-embedding-3-small")
            or "text-embedding-3-small"
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
    gemini_embedding_model: str = Field(
        default_factory=lambda: (
            _env_str("GEMINI_EMBEDDING_MODEL", "text-embedding-004")
            or "text-embedding-004"
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
    vertex_embedding_model: str = Field(
        default_factory=lambda: (
            _env_str("VERTEX_EMBEDDING_MODEL", "text-embedding-005")
            or "text-embedding-005"
        )
    )

    use_neo4j: bool = Field(
        default_factory=lambda: _env_bool("USE_NEO4J", True)
    )
    neo4j_uri: Optional[str] = Field(
        default_factory=lambda: _env_str("NEO4J_URI", "bolt://127.0.0.1:7687")
    )
    neo4j_user: Optional[str] = Field(
        default_factory=lambda: _env_str("NEO4J_USER", "neo4j")
    )
    neo4j_password: Optional[str] = Field(
        default_factory=lambda: _env_str("NEO4J_PASSWORD", "password")
    )
    neo4j_ingest_batch_size: int = Field(
        default_factory=lambda: _env_int("NEO4J_INGEST_BATCH_SIZE", 500)
    )
    neo4j_ingest_max_retries: int = Field(
        default_factory=lambda: _env_int("NEO4J_INGEST_MAX_RETRIES", 2)
    )
    neo4j_ingest_retry_delay_ms: int = Field(
        default_factory=lambda: _env_int("NEO4J_INGEST_RETRY_DELAY_MS", 150)
    )

    use_rq: bool = Field(default_factory=lambda: _env_bool("USE_RQ", False))
    redis_url: str = Field(
        default_factory=lambda: (
            _env_str("REDIS_URL", "redis://localhost:6379/0")
            or "redis://localhost:6379/0"
        )
    )
    rq_ingest_job_timeout_sec: int = Field(
        default_factory=lambda: _env_int("RQ_INGEST_JOB_TIMEOUT_SEC", 900)
    )

    @field_validator("rq_ingest_job_timeout_sec")
    @classmethod
    def validate_rq_ingest_job_timeout_sec(cls, value: int) -> int:
        """Ensure RQ ingest timeout is a positive integer."""
        if value <= 0:
            raise ValueError("RQ_INGEST_JOB_TIMEOUT_SEC must be > 0")
        return value

    @staticmethod
    def _resolve_repo_path(path_value: Path) -> Path:
        """Resolve relative paths against repository root."""
        if path_value.is_absolute():
            return path_value
        return (REPO_ROOT / path_value).resolve()

    @model_validator(mode="after")
    def normalize_paths(self) -> "Settings":
        """Normalize workspace and storage paths to absolute locations."""
        self.workspace_dir = self._resolve_repo_path(self.workspace_dir)
        self.data_dir = self._resolve_repo_path(self.data_dir)
        self.chroma_persist_dir = self._resolve_repo_path(
            self.chroma_persist_dir
        )
        return self

    @staticmethod
    def _normalize_provider_name(provider: str) -> str:
        """Normalize provider aliases used in env values and requests."""
        normalized = provider.strip().lower()
        if normalized == "vertex_ai":
            return "vertex"
        return normalized

    def resolve_llm_provider(self, override: Optional[str] = None) -> str:
        """Resolve effective provider considering request override."""
        provider_name = override or self.llm_provider
        return self._normalize_provider_name(provider_name)

    def resolve_embedding_provider(
        self,
        override: Optional[str] = None,
    ) -> str:
        """Resolve provider used for embeddings."""
        provider_name = override or self.llm_provider
        return self._normalize_provider_name(provider_name)

    def resolve_embedding_model(
        self,
        provider_override: Optional[str] = None,
        model_override: Optional[str] = None,
    ) -> str:
        """Resolve embedding model with global override precedence."""
        if model_override and model_override.strip():
            return model_override.strip()
        if self.llm_embedding and self.llm_embedding.strip():
            return self.llm_embedding.strip()

        provider_name = self.resolve_embedding_provider(provider_override)
        if provider_name == "openai":
            return self.openai_embedding_model
        if provider_name == "gemini":
            return self.gemini_embedding_model
        if provider_name == "vertex":
            return self.vertex_embedding_model
        raise ValueError(
            "Embedding provider must be openai, gemini or vertex. "
            f"Received: {provider_name}"
        )

    def resolve_answer_model(
        self,
        provider_override: Optional[str] = None,
    ) -> Optional[str]:
        """Resolve answer model configured for the selected provider."""
        provider_name = self.resolve_llm_provider(provider_override)
        if provider_name == "local":
            return None
        if provider_name == "openai":
            return self.openai_answer_model
        if provider_name == "gemini":
            return self.gemini_answer_model
        if provider_name == "vertex":
            return self.vertex_answer_model
        raise ValueError(
            "Answer provider must be local, openai, gemini or vertex. "
            f"Received: {provider_name}"
        )

    def is_provider_configured(self, provider: str) -> bool:
        """Check whether provider credentials are available."""
        provider_name = self._normalize_provider_name(provider)
        if provider_name == "openai":
            return bool(self.openai_api_key)
        if provider_name == "gemini":
            return bool(self.gemini_api_key)
        if provider_name == "vertex":
            return bool(self.vertex_ai_api_key and self.vertex_project_id)
        return False

    def require_chroma_enabled(self) -> None:
        """Fail fast when runtime is not configured for Chroma vector store."""
        if not self.use_chroma:
            raise RuntimeError(
                "USE_CHROMA must be true. This runtime requires ChromaDB "
                "for vector storage and search."
            )

    def require_neo4j_enabled(self) -> None:
        """Fail fast when runtime is not configured for Neo4j graph store."""
        if not self.use_neo4j:
            raise RuntimeError(
                "USE_NEO4J must be true. This runtime requires Neo4j "
                "for graph persistence and traversal."
            )
        if not self.neo4j_uri:
            raise RuntimeError(
                "NEO4J_URI is required when Neo4j is mandatory at runtime."
            )
        if not self.neo4j_user or not self.neo4j_password:
            raise RuntimeError(
                "NEO4J_USER and NEO4J_PASSWORD are required when Neo4j is "
                "mandatory at runtime."
            )

    def require_embedding_provider_configured(
        self,
        provider: Optional[str] = None,
    ) -> str:
        """Validate embedding provider and credentials in strict mode."""
        provider_name = self.resolve_embedding_provider(provider)
        if provider_name not in {"openai", "gemini", "vertex"}:
            raise RuntimeError(
                "Unsupported embedding provider. Configure LLM_PROVIDER "
                "as openai, gemini or vertex."
            )
        if not self.is_provider_configured(provider_name):
            raise RuntimeError(
                "Embedding provider credentials are missing for "
                f"'{provider_name}'."
            )
        return provider_name


SETTINGS = Settings()
