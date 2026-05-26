"""TDM ingestion service extracted from the runtime facade."""

from __future__ import annotations

from collections.abc import Callable

from coderag.core.models import IngestionRequest
from coderag.core.protocols import GraphStoreProtocol, RuntimeStoreProtocol
from coderag.ingestion.tdm_graph_builder import build_tdm_typed_edges
from coderag.ingestion.tdm_ingestion import ingest_tdm_assets


class TdmIngestionApplicationService:
    """Own additive TDM ingestion and graph sync operations."""

    def __init__(
        self,
        *,
        store: RuntimeStoreProtocol,
        graph_store: GraphStoreProtocol,
        ensure_tdm_graph_enabled: Callable[[], None],
    ) -> None:
        """Build TDM ingestion service from runtime collaborators."""
        self._store = store
        self._graph_store = graph_store
        self._ensure_tdm_graph_enabled = ensure_tdm_graph_enabled

    def ingest_tdm_assets(self, request: IngestionRequest) -> dict[str, object]:
        """Ingest TDM assets and refresh typed TDM graph edges."""
        self._ensure_tdm_graph_enabled()

        summary = ingest_tdm_assets(
            source=request.source,
            store=self._store,
        )
        source_id = str(summary.get("source_id", ""))
        if source_id:
            schemas = self._store.list_tdm_schemas(source_id=source_id)
            tables = self._store.list_tdm_tables(source_id=source_id)
            columns = self._store.list_tdm_columns(source_id=source_id)
            mappings = self._store.list_tdm_service_mappings(
                source_id=source_id,
            )
            masking_rules = self._store.list_tdm_masking_rules(
                source_id=source_id,
            )
            typed_edges = build_tdm_typed_edges(
                source_id=source_id,
                schemas=schemas,
                tables=tables,
                columns=columns,
                mappings=mappings,
                masking_rules=masking_rules,
            )
            graph_metrics = self._graph_store.replace_tdm_edges(
                source_id=source_id,
                typed_edges=typed_edges,
            )
            summary["tdm_graph_edges"] = len(typed_edges)
            summary["tdm_graph_batches"] = int(
                graph_metrics.get("batches_written", 0)
            )

        return {
            "status": "completed",
            **summary,
        }