"""Data contracts used across ingestion and query pipelines."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class SourceConfig(BaseModel):
    """Configuration for a source ingestion request."""

    source_type: str = "folder"
    source_url: Optional[str] = None
    base_url: Optional[str] = None
    token: Optional[str] = None
    local_path: Optional[str] = None
    filters: Dict[str, Any] = Field(default_factory=dict)


class IngestionRequest(BaseModel):
    """API contract for ingestion entrypoint."""

    source: SourceConfig


class ResetAllRequest(BaseModel):
    """API contract for destructive full reset operation."""

    confirm: bool = False


class ResetAllResponse(BaseModel):
    """Response payload for full reset operation."""

    status: str
    message: str
    deleted_documents: int
    deleted_chunks: int
    deleted_graph_edges: int
    deleted_jobs: int
    neo4j_enabled: bool
    neo4j_edges_deleted: int


class DocumentRecord(BaseModel):
    """Canonical document object inside local storage."""

    document_id: str
    source_id: str
    title: str
    content: str
    path_or_url: str
    content_type: str
    updated_at: datetime
    metadata: Dict[str, Any] = Field(default_factory=dict)


class ChunkRecord(BaseModel):
    """Semantic chunk used by retrieval indexes."""

    chunk_id: str
    document_id: str
    source_id: str
    section_name: str
    text: str
    start_ref: int
    end_ref: int
    entity_name: Optional[str] = None
    entity_type: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


class Evidence(BaseModel):
    """Evidence returned to users for traceability."""

    chunk_id: str
    document_id: str
    score: float
    snippet: str
    path_or_url: str
    section_name: str
    start_ref: int
    end_ref: int


class GraphPath(BaseModel):
    """Graph traversal path shown as supporting rationale."""

    nodes: List[str]
    relationships: List[str]


class QueryRequest(BaseModel):
    """Query API payload."""

    question: str
    source_id: Optional[str] = None
    hops: Optional[int] = None
    llm_provider: Optional[str] = None
    force_fallback: bool = False


class QueryResponse(BaseModel):
    """Query API output payload."""

    answer: str
    citations: List[Evidence]
    graph_paths: List[GraphPath]
    diagnostics: Dict[str, Any]


class JobStatus(BaseModel):
    """Background job tracking contract."""

    job_id: str
    status: str
    message: str
    created_at: datetime
    updated_at: datetime
