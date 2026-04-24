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


class DocumentCatalogEntry(BaseModel):
    """Lightweight document metadata exposed to UI selectors."""

    document_id: str
    source_id: str
    title: str
    path_or_url: str
    content_type: str
    updated_at: datetime


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
    document_ids: List[str] = Field(default_factory=list)
    hops: Optional[int] = None
    llm_provider: Optional[str] = None
    force_fallback: bool = False
    include_llm_answer: bool = True


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


class TdmSchemaAsset(BaseModel):
    """Schema-level TDM metadata captured from technical sources."""

    schema_id: str
    source_id: str
    database_name: str
    schema_name: str
    metadata: Dict[str, Any] = Field(default_factory=dict)


class TdmTableAsset(BaseModel):
    """Table-level TDM metadata mapped to one schema."""

    table_id: str
    source_id: str
    schema_id: str
    table_name: str
    table_type: str = "table"
    metadata: Dict[str, Any] = Field(default_factory=dict)


class TdmColumnAsset(BaseModel):
    """Column-level TDM metadata including sensitivity hints."""

    column_id: str
    source_id: str
    table_id: str
    column_name: str
    data_type: str
    nullable: bool = True
    pii_class: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


class TdmServiceMapping(BaseModel):
    """Maps service/API contracts to backing table assets."""

    mapping_id: str
    source_id: str
    service_name: str
    endpoint: str
    method: str
    table_id: str
    metadata: Dict[str, Any] = Field(default_factory=dict)


class TdmMaskingRule(BaseModel):
    """Masking policy definition linked to table/column scope."""

    rule_id: str
    source_id: str
    rule_name: str
    policy_type: str
    scope: str
    table_id: Optional[str] = None
    column_id: Optional[str] = None
    priority: int = 100
    metadata: Dict[str, Any] = Field(default_factory=dict)


class TdmSyntheticProfile(BaseModel):
    """Synthetic data profile instructions for TDM generation workflows."""

    profile_id: str
    source_id: str
    profile_name: str
    target_table_id: Optional[str] = None
    strategy: str = "template"
    metadata: Dict[str, Any] = Field(default_factory=dict)


class TdmVirtualizationArtifact(BaseModel):
    """Virtualization artifact generated for API/service test environments."""

    artifact_id: str
    source_id: str
    service_name: str
    artifact_type: str
    content_json: Dict[str, Any] = Field(default_factory=dict)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class TdmIngestRequest(BaseModel):
    """Request payload for additive TDM ingestion routes."""

    source: SourceConfig
    include_masking_hints: bool = True
    include_virtualization_hints: bool = True


class TdmQueryRequest(BaseModel):
    """Request payload for TDM agent-facing query routes."""

    question: str
    source_id: Optional[str] = None
    service_name: Optional[str] = None
    table_name: Optional[str] = None
    include_virtualization_preview: bool = False


class TdmQueryResponse(BaseModel):
    """Response payload for additive TDM query routes."""

    answer: str
    findings: List[Dict[str, Any]] = Field(default_factory=list)
    diagnostics: Dict[str, Any] = Field(default_factory=dict)
