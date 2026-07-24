"""Data contracts used across ingestion and query pipelines."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator


class SourceConfig(BaseModel):
    """Configuration for a source ingestion request."""

    source_type: str = "folder"
    source_url: str | None = None
    base_url: str | None = None
    token: str | None = None
    local_path: str | None = None
    logical_root: str | None = None
    artifact_id: str | None = None
    filters: dict[str, Any] = Field(default_factory=dict)
    tags: list[str] = Field(default_factory=list)


class IngestionRequest(BaseModel):
    """API contract for ingestion entrypoint."""

    source: SourceConfig


class ResetAllResponse(BaseModel):
    """Response payload for full reset operation."""

    status: str
    message: str
    deleted_documents: int
    deleted_chunks: int
    deleted_jobs: int
    neo4j_enabled: bool
    neo4j_edges_deleted: int


class AdminResetRequest(BaseModel):
    """Request payload required to authorize a global administrative reset."""

    confirm: Literal[True] = Field(
        description="Must be true to confirm the destructive operation."
    )
    confirmation_phrase: str = Field(
        description="Explicit confirmation phrase required by the endpoint.",
        examples=["RESET ALL DATA"],
    )

    @field_validator("confirmation_phrase", mode="before")
    @classmethod
    def normalize_confirmation_phrase(cls, value: Any) -> str | Any:
        """Trim confirmation text before validating the contract."""
        if not isinstance(value, str):
            return value
        return value.strip()

    @model_validator(mode="after")
    def validate_confirmation_phrase(self) -> "AdminResetRequest":
        """Require the exact human confirmation phrase."""
        if self.confirmation_phrase != "RESET ALL DATA":
            raise ValueError(
                "confirmation_phrase must be exactly 'RESET ALL DATA'"
            )
        return self


class DeleteDocumentResponse(BaseModel):
    """Response payload for deleting one persisted document."""

    status: str
    message: str
    document_id: str
    source_id: str
    deleted_documents: int
    deleted_chunks: int
    deleted_staging_files: int
    reindexed_sources: int
    neo4j_nodes_deleted: int = 0
    created: bool = Field(
        default=False,
        description=(
            "Contrato Hexa: idempotencia de tools de escritura. Siempre "
            "false para delete_document (mutación sobre documento existente)."
        ),
    )


class ReplaceDocumentTagsRequest(BaseModel):
    """Request payload for replacing document tags."""

    tags: list[str] = Field(default_factory=list)


class DocumentTagFacet(BaseModel):
    """Aggregated tag facet with persisted document count."""

    tag: str
    document_count: int


class ListDocumentTagsResponse(BaseModel):
    """Response payload for aggregated document tags."""

    source_id: str | None = None
    count: int
    tags: list[str] = Field(default_factory=list)
    items: list[DocumentTagFacet] = Field(default_factory=list)


class ReplaceDocumentTagsResponse(BaseModel):
    """Response payload for replacing document tags."""

    status: str
    message: str
    document_id: str
    source_id: str
    old_tags: list[str] = Field(default_factory=list)
    new_tags: list[str] = Field(default_factory=list)
    created: bool = Field(
        default=False,
        description=(
            "Contrato Hexa: idempotencia de tools de escritura. Siempre "
            "false para replace_document_tags (mutación sobre documento "
            "existente)."
        ),
    )


class DocumentRecord(BaseModel):
    """Canonical document object inside local storage."""

    document_id: str
    source_id: str
    title: str
    content: str
    path_or_url: str
    content_type: str
    updated_at: datetime
    tags: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class DocumentCatalogEntry(BaseModel):
    """Lightweight document metadata exposed to UI selectors."""

    document_id: str
    source_id: str
    title: str
    path_or_url: str
    content_type: str
    updated_at: datetime
    tags: list[str] = Field(default_factory=list)


class DocumentContentResponse(BaseModel):
    """Public API payload exposing one persisted document and its content."""

    document_id: str
    source_id: str
    title: str
    content: str
    path_or_url: str
    content_type: str
    updated_at: datetime
    tags: list[str] = Field(default_factory=list)


class UploadedFilePayload(BaseModel):
    """One file uploaded via JSON body with base64-encoded content.

    MCP-friendly alternative to multipart ``UploadFile``: an AI agent can fill
    these fields as plain JSON arguments to attach files over the MCP transport.
    """

    filename: str = Field(min_length=1)
    content_base64: str = Field(min_length=1)
    media_type: str | None = None


class FilesIngestionJsonRequest(BaseModel):
    """JSON request to ingest one batch of base64-encoded uploaded files."""

    files: list[UploadedFilePayload] = Field(min_length=1)
    source_type: str = "folder"
    filters: dict[str, Any] = Field(default_factory=dict)
    tags: list[str] = Field(default_factory=list)


class ChunkRecord(BaseModel):
    """Semantic chunk used by retrieval indexes."""

    chunk_id: str
    document_id: str
    source_id: str
    section_name: str
    text: str
    start_ref: int
    end_ref: int
    entity_name: str | None = None
    entity_type: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


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

    nodes: list[str]
    relationships: list[str]


class QueryRequest(BaseModel):
    """Query API payload."""

    question: str
    source_id: str | None = None
    document_ids: list[str] = Field(default_factory=list)
    hops: int | None = None
    llm_provider: str | None = None
    force_fallback: bool = False
    include_llm_answer: bool = True


class QueryResponse(BaseModel):
    """Query API output payload."""

    answer: str
    citations: list[Evidence]
    graph_paths: list[GraphPath]
    diagnostics: dict[str, Any]


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
    metadata: dict[str, Any] = Field(default_factory=dict)


class TdmTableAsset(BaseModel):
    """Table-level TDM metadata mapped to one schema."""

    table_id: str
    source_id: str
    schema_id: str
    table_name: str
    table_type: str = "table"
    metadata: dict[str, Any] = Field(default_factory=dict)


class TdmColumnAsset(BaseModel):
    """Column-level TDM metadata including sensitivity hints."""

    column_id: str
    source_id: str
    table_id: str
    column_name: str
    data_type: str
    nullable: bool = True
    pii_class: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class TdmServiceMapping(BaseModel):
    """Maps service/API contracts to backing table assets."""

    mapping_id: str
    source_id: str
    service_name: str
    endpoint: str
    method: str
    table_id: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class TdmMaskingRule(BaseModel):
    """Masking policy definition linked to table/column scope."""

    rule_id: str
    source_id: str
    rule_name: str
    policy_type: str
    scope: str
    table_id: str | None = None
    column_id: str | None = None
    priority: int = 100
    metadata: dict[str, Any] = Field(default_factory=dict)


class TdmSyntheticProfile(BaseModel):
    """Synthetic data profile instructions for TDM generation workflows."""

    profile_id: str
    source_id: str
    profile_name: str
    target_table_id: str | None = None
    strategy: str = "template"
    metadata: dict[str, Any] = Field(default_factory=dict)


class TdmVirtualizationArtifact(BaseModel):
    """Virtualization artifact generated for API/service test environments."""

    artifact_id: str
    source_id: str
    service_name: str
    artifact_type: str
    content_json: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)


class TdmIngestRequest(BaseModel):
    """Request payload for additive TDM ingestion routes."""

    source: SourceConfig
    include_masking_hints: bool = True
    include_virtualization_hints: bool = True


class TdmQueryRequest(BaseModel):
    """Request payload for TDM agent-facing query routes."""

    question: str
    source_id: str | None = None
    service_name: str | None = None
    table_name: str | None = None
    include_virtualization_preview: bool = False


class TdmQueryResponse(BaseModel):
    """Response payload for additive TDM query routes."""

    answer: str
    findings: list[dict[str, Any]] = Field(default_factory=list)
    diagnostics: dict[str, Any] = Field(default_factory=dict)


class McpInfoResponse(BaseModel):
    """Metadata publicada en GET /info, contrato de integración MCP Hexa."""

    name: str = Field(description="Nombre único del servidor MCP.")
    version: str = Field(description="Versión semántica del servicio.")
    server_type: Literal["tools", "agent"] = Field(
        description="tools: operaciones discretas y sincrónicas."
    )
    description: str = Field(description="Breve descripción del sistema integrado.")
    sensitive_fields: list[str] = Field(
        description=(
            "Campos que pueden contener datos libres ingresados por "
            "usuarios, usados por Hexa para configurar el DualLLM Sanitizer."
        )
    )


class McpDependencyStatus(BaseModel):
    """Estado de una dependencia individual reportada en GET /health."""

    status: Literal["healthy", "unhealthy"] = Field(
        description="Salud de la dependencia evaluada."
    )
    latency_ms: float = Field(description="Latencia del chequeo en milisegundos.")


class McpHealthResponse(BaseModel):
    """Shape de GET /health exigido por el contrato de integración MCP Hexa."""

    status: Literal["healthy", "degraded", "unhealthy"] = Field(
        description="Estado global consolidado del servicio."
    )
    name: str = Field(description="Nombre del servidor MCP.")
    version: str = Field(description="Versión semántica del servicio.")
    uptime_s: int = Field(description="Segundos transcurridos desde el arranque.")
    dependencies: dict[str, McpDependencyStatus] = Field(
        default_factory=dict,
        description="Estado por dependencia crítica/no crítica evaluada.",
    )
