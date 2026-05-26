"""TDM query and catalog service extracted from the application facade."""

from __future__ import annotations

from collections.abc import Callable

from coderag.core.models import TdmQueryRequest, TdmQueryResponse
from coderag.core.protocols import GraphStoreProtocol, RuntimeStoreProtocol
from coderag.core.settings import Settings
from coderag.tdm.masking_engine import apply_masking_rules_to_row
from coderag.tdm.synthetic_planner import build_synthetic_profile_plan
from coderag.tdm.virtualization_export import build_virtualization_templates


class TdmQueryApplicationService:
    """Own TDM query, catalog, and planning operations."""

    def __init__(
        self,
        *,
        store: RuntimeStoreProtocol,
        graph_store: GraphStoreProtocol,
        settings: Settings,
        ensure_tdm_graph_enabled: Callable[[], None],
    ) -> None:
        """Build TDM query service from runtime collaborators."""
        self._store = store
        self._graph_store = graph_store
        self._settings = settings
        self._ensure_tdm_graph_enabled = ensure_tdm_graph_enabled

    def query_tdm(self, request: TdmQueryRequest) -> TdmQueryResponse:
        """Run TDM catalog query mode for agent-facing workflows."""
        self._ensure_tdm_graph_enabled()

        tables = self._store.list_tdm_tables(source_id=request.source_id)
        columns = self._store.list_tdm_columns(source_id=request.source_id)
        mappings = self._store.list_tdm_service_mappings(
            source_id=request.source_id,
        )
        masking_rules = self._store.list_tdm_masking_rules(
            source_id=request.source_id,
        )

        findings: list[dict[str, object]] = []
        if request.service_name:
            findings.extend(
                item
                for item in mappings
                if str(item.get("service_name", "")).casefold()
                == request.service_name.casefold()
            )
        if request.table_name:
            matching_tables = [
                table
                for table in tables
                if str(table.get("table_name", "")).casefold()
                == request.table_name.casefold()
            ]
            findings.extend(matching_tables)

            matched_table_ids = {
                str(table.get("table_id"))
                for table in matching_tables
                if table.get("table_id")
            }
            findings.extend(
                column
                for column in columns
                if str(column.get("table_id", "")) in matched_table_ids
            )

        if not findings:
            findings = mappings[:10]

        if self._settings.tdm_enable_masking and findings:
            self._apply_masking_preview(findings=findings, masking_rules=masking_rules)

        tdm_paths = self._graph_store.expand_tdm_paths(
            query=request.question,
            hops=2,
            max_paths=6,
            source_id=request.source_id,
        )
        answer = (
            f"TDM query processed for '{request.question}'. "
            f"Found {len(findings)} catalog items and {len(tdm_paths)} graph paths."
        )

        return TdmQueryResponse(
            answer=answer,
            findings=list(findings),
            diagnostics={
                "tables": len(tables),
                "columns": len(columns),
                "service_mappings": len(mappings),
                "masking_rules": len(masking_rules),
                "graph_paths": len(tdm_paths),
                "service_filter": request.service_name,
                "table_filter": request.table_name,
                "source_id": request.source_id,
                "masking_enabled": self._settings.tdm_enable_masking,
                "synthetic_enabled": self._settings.tdm_enable_synthetic,
                "virtualization_enabled": self._settings.tdm_enable_virtualization,
            },
        )

    def get_tdm_service_catalog(
        self,
        service_name: str,
        source_id: str | None = None,
    ) -> dict[str, object]:
        """Return TDM catalog data for one service name."""
        self._ensure_tdm_graph_enabled()
        mappings = self._store.list_tdm_service_mappings(source_id=source_id)
        selected = [
            item
            for item in mappings
            if str(item.get("service_name", "")).casefold()
            == service_name.casefold()
        ]
        return {
            "service_name": service_name,
            "source_id": source_id,
            "mappings": selected,
            "count": len(selected),
        }

    def get_tdm_table_catalog(
        self,
        table_name: str,
        source_id: str | None = None,
    ) -> dict[str, object]:
        """Return TDM catalog data for one table name."""
        self._ensure_tdm_graph_enabled()
        tables = self._store.list_tdm_tables(source_id=source_id)
        matched_tables = [
            table
            for table in tables
            if str(table.get("table_name", "")).casefold()
            == table_name.casefold()
        ]
        table_ids = {
            str(table.get("table_id"))
            for table in matched_tables
            if table.get("table_id")
        }
        columns = [
            column
            for column in self._store.list_tdm_columns(source_id=source_id)
            if str(column.get("table_id", "")) in table_ids
        ]
        return {
            "table_name": table_name,
            "source_id": source_id,
            "tables": matched_tables,
            "columns": columns,
            "count": len(matched_tables),
        }

    def preview_tdm_virtualization(
        self,
        request: TdmQueryRequest,
    ) -> dict[str, object]:
        """Build lightweight virtualization preview from TDM catalog data."""
        self._ensure_tdm_graph_enabled()
        if not self._settings.tdm_enable_virtualization:
            raise RuntimeError(
                "TDM virtualization is disabled. Set "
                "TDM_ENABLE_VIRTUALIZATION=true to enable."
            )

        mappings = self._store.list_tdm_service_mappings(
            source_id=request.source_id,
        )
        templates = build_virtualization_templates(
            source_id=request.source_id or "global",
            mappings=mappings,
            service_name_filter=request.service_name,
        )[:20]

        for template in templates:
            self._store.upsert_tdm_virtualization_artifact(
                artifact_id=str(template.get("artifact_id")),
                source_id=str(request.source_id or "global"),
                service_name=str(template.get("service_name")),
                artifact_type=str(template.get("artifact_type")),
                content=dict(template.get("content") or {}),
                metadata=dict(template.get("metadata") or {}),
            )

        return {
            "source_id": request.source_id,
            "service_name": request.service_name,
            "templates": templates,
            "count": len(templates),
        }

    def get_tdm_synthetic_profile(
        self,
        table_name: str,
        source_id: str | None = None,
        target_rows: int = 1000,
    ) -> dict[str, object]:
        """Build and persist a synthetic profile plan for one table."""
        self._ensure_tdm_graph_enabled()
        if not self._settings.tdm_enable_synthetic:
            raise RuntimeError(
                "TDM synthetic planning is disabled. Set "
                "TDM_ENABLE_SYNTHETIC=true to enable."
            )

        table_catalog = self.get_tdm_table_catalog(
            table_name=table_name,
            source_id=source_id,
        )
        columns = list(table_catalog.get("columns", []))
        plan = build_synthetic_profile_plan(
            table_name=table_name,
            columns=columns,
            target_rows=target_rows,
        )

        profile_id = (
            f"syn-{table_name.casefold().replace(' ', '-')}-"
            f"{max(1, int(target_rows))}"
        )
        table_rows = list(table_catalog.get("tables", []))
        target_table_id = None
        if table_rows:
            target_table_id = table_rows[0].get("table_id")

        self._store.upsert_tdm_synthetic_profile(
            profile_id=profile_id,
            source_id=source_id or "global",
            profile_name=f"synthetic-{table_name}",
            strategy="template",
            target_table_id=str(target_table_id) if target_table_id else None,
            metadata={"plan": plan},
        )

        return {
            "source_id": source_id,
            "table_name": table_name,
            "profile_id": profile_id,
            "plan": plan,
        }

    def _apply_masking_preview(
        self,
        *,
        findings: list[dict[str, object]],
        masking_rules: list[dict[str, object]],
    ) -> None:
        """Attach masking previews to findings that map to one column id."""
        masking_rules_by_column: dict[str, list[dict[str, object]]] = {}
        for rule in masking_rules:
            column_id = str(rule.get("column_id") or "").strip()
            if not column_id:
                continue
            masking_rules_by_column.setdefault(column_id, []).append(rule)

        for item in findings:
            if not isinstance(item, dict):
                continue
            column_id = str(item.get("column_id") or "").strip()
            if not column_id:
                continue
            rules = masking_rules_by_column.get(column_id, [])
            if not rules:
                continue
            preview_input = {
                str(item.get("column_name") or "column"):
                f"sample_{item.get('column_name', 'value')}"
            }
            preview_rules = [
                {
                    "column_name": str(item.get("column_name") or ""),
                    "policy_type": str(rule.get("policy_type") or "mask"),
                }
                for rule in rules
            ]
            item["masking_preview"] = apply_masking_rules_to_row(
                row=preview_input,
                rules=preview_rules,
                seed="tdm-preview",
            )