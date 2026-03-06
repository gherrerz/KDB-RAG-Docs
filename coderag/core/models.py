"""Pydantic data models for requests, jobs, and retrieval objects."""

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class JobStatus(str, Enum):
    """Supported lifecycle states for ingestion jobs."""

    queued = "queued"
    running = "running"
    completed = "completed"
    failed = "failed"


class RepoIngestRequest(BaseModel):
    """Input model for repository ingestion requests."""

    provider: str = Field(default="github")
    repo_url: str
    token: str | None = None
    branch: str = "main"
    commit: str | None = None


class JobInfo(BaseModel):
    """Current state snapshot for an ingestion job."""

    id: str
    status: JobStatus
    progress: float = 0.0
    logs: list[str] = Field(default_factory=list)
    repo_id: str | None = None
    error: str | None = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class QueryRequest(BaseModel):
    """Input model for user natural language questions."""

    repo_id: str
    query: str
    top_n: int = 80
    top_k: int = 20


class InventoryQueryRequest(BaseModel):
    """Input model for graph-first inventory queries."""

    repo_id: str
    query: str
    page: int = 1
    page_size: int = 80


class Citation(BaseModel):
    """Evidence metadata for each supported claim in an answer."""

    path: str
    start_line: int
    end_line: int
    score: float
    reason: str


class QueryResponse(BaseModel):
    """Output model returned by query endpoint."""

    answer: str
    citations: list[Citation]
    diagnostics: dict[str, Any] = Field(default_factory=dict)


class InventoryItem(BaseModel):
    """Structured inventory item discovered in repository graph."""

    label: str
    path: str
    kind: str = "file"
    start_line: int = 1
    end_line: int = 1


class InventoryQueryResponse(BaseModel):
    """Output model returned by paginated inventory endpoint."""

    answer: str
    target: str | None = None
    module_name: str | None = None
    total: int = 0
    page: int = 1
    page_size: int = 80
    items: list[InventoryItem] = Field(default_factory=list)
    citations: list[Citation] = Field(default_factory=list)
    diagnostics: dict[str, Any] = Field(default_factory=dict)


class ResetResponse(BaseModel):
    """Output model returned by full reset endpoint."""

    message: str
    cleared: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class RepoCatalogResponse(BaseModel):
    """Output model for repository identifiers available for querying."""

    repo_ids: list[str] = Field(default_factory=list)


class ScannedFile(BaseModel):
    """Represents a source file discovered in a repository scan."""

    path: str
    language: str
    content: str


class SymbolChunk(BaseModel):
    """Symbol-level chunk extracted from a source file."""

    id: str
    repo_id: str
    path: str
    language: str
    symbol_name: str
    symbol_type: str
    start_line: int
    end_line: int
    snippet: str


class RetrievalChunk(BaseModel):
    """Chunk returned from vector/BM25/graph retrieval."""

    id: str
    text: str
    score: float
    metadata: dict[str, Any]
