"""Tests for module discovery support in query service."""

from pathlib import Path

import pytest

import coderag.api.query_service as query_service
from coderag.core.models import Citation


def test_is_module_query_detects_spanish_and_english_terms() -> None:
    """Identifies module-related query intents in common variants."""
    assert query_service._is_module_query("Cuales son los modulos?")
    assert query_service._is_module_query("list repository modules")
    assert not query_service._is_module_query("donde se define auth")


def test_discover_repo_modules_reads_top_level_dirs(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Returns generic top-level module folders from local repository."""
    repo_id = "repo1"
    repo_dir = tmp_path / repo_id
    (repo_dir / "api-service").mkdir(parents=True)
    (repo_dir / "web-client").mkdir(parents=True)
    (repo_dir / "docs").mkdir(parents=True)
    (repo_dir / "node_modules").mkdir(parents=True)

    class _Settings:
        workspace_path = tmp_path

    monkeypatch.setattr(query_service, "get_settings", lambda: _Settings())

    modules = query_service._discover_repo_modules(repo_id)
    assert "api-service" in modules
    assert "web-client" in modules
    assert "docs" not in modules
    assert "node_modules" not in modules


def test_is_inventory_query_detection() -> None:
    """Detects generic inventory intents in natural language queries."""
    assert query_service._is_inventory_query(
        "cuales son todos los service del modulo api-service"
    )
    assert query_service._is_inventory_query("list all controllers in module")
    assert not query_service._is_inventory_query("que hace autenticacion")


def test_extract_inventory_target_for_es_and_en() -> None:
    """Extracts normalized inventory target token from user query."""
    assert query_service._extract_inventory_target("todos los services del modulo") == "service"
    assert query_service._extract_inventory_target("all controllers in api-service") == "controller"
    assert (
        query_service._extract_inventory_target(
            "cuales son todos los controladores de mall-portal"
        )
        == "controlador"
    )


def test_inventory_term_aliases_expand_for_multilingual_queries() -> None:
    """Expands inventory target to include plural and cross-language aliases."""
    aliases = query_service._inventory_term_aliases("servicios")
    assert "servicio" in aliases
    assert "service" in aliases
    assert "services" in aliases
    assert "servicees" not in aliases


def test_inventory_term_aliases_expand_for_controllers() -> None:
    """Expands spanish plural controllers to canonical english/spanish variants."""
    aliases = query_service._inventory_term_aliases("controladores")
    assert "controlador" in aliases
    assert "controladores" in aliases
    assert "controller" in aliases
    assert "controllers" in aliases


def test_query_inventory_entities_merges_alias_matches(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Merges and deduplicates inventory matches coming from alias terms."""

    class _Graph:
        def __init__(self) -> None:
            self.seen_terms: list[str] = []

        def query_inventory(
            self,
            repo_id: str,
            target_term: str,
            module_name: str | None,
            limit: int,
        ) -> list[dict]:
            self.seen_terms.append(target_term)
            if target_term == "service":
                return [
                    {
                        "label": "HomeService.java",
                        "path": "src/HomeService.java",
                        "start_line": 1,
                        "end_line": 1,
                    }
                ]
            if target_term == "servicio":
                return [
                    {
                        "label": "HomeService.java",
                        "path": "src/HomeService.java",
                        "start_line": 1,
                        "end_line": 1,
                    },
                    {
                        "label": "OrderService.java",
                        "path": "src/OrderService.java",
                        "start_line": 1,
                        "end_line": 1,
                    },
                ]
            return []

        def close(self) -> None:
            return None

    graph = _Graph()
    monkeypatch.setattr(query_service, "GraphBuilder", lambda: graph)

    entities = query_service._query_inventory_entities(
        repo_id="repo1",
        target_term="servicios",
        module_name=None,
    )
    paths = [item["path"] for item in entities]

    assert "service" in graph.seen_terms
    assert "servicio" in graph.seen_terms
    assert paths == ["src/HomeService.java", "src/OrderService.java"]


def test_extract_module_name_is_generic() -> None:
    """Extracts module names from generic spanish/english query phrasing."""
    assert query_service._extract_module_name("modulo api-service") == "api-service"
    assert query_service._extract_module_name("in web/client") == "web/client"
    assert (
        query_service._extract_module_name(
            "traeme todos los servicios de mall-portal"
        )
        == "mall-portal"
    )


def test_extractive_fallback_limits_non_inventory_results() -> None:
    """Shows a compact extractive list for non-inventory queries."""
    citations = [
        Citation(
            path=f"src/File{i}.java",
            start_line=1,
            end_line=1,
            score=1.0,
            reason="inventory_graph_match",
        )
        for i in range(1, 8)
    ]
    answer = query_service._build_extractive_fallback(citations)
    assert "1. src/File1.java" in answer
    assert "5. src/File5.java" in answer
    assert "6. src/File6.java" not in answer


def test_extractive_fallback_lists_all_inventory_results() -> None:
    """Builds structured full inventory answer in extractive mode."""
    citations = [
        Citation(
            path=f"src/File{i}.java",
            start_line=1,
            end_line=1,
            score=1.0,
            reason="inventory_graph_match",
        )
        for i in range(1, 8)
    ]
    answer = query_service._build_extractive_fallback(
        citations,
        inventory_mode=True,
        inventory_target="controller",
        query="dame todos los controllers",
    )
    assert "1) Respuesta principal:" in answer
    assert "2) Componentes/archivos clave:" in answer
    assert "3) Organización observada en el contexto:" in answer
    assert "4) Citas de archivos con líneas:" in answer
    assert "- File1.java" in answer
    assert "- File7.java" in answer
    assert "Consulta original: dame todos los controllers" in answer


def test_extractive_fallback_verification_failed_message() -> None:
    """Uses verification_failed message and avoids not_configured text."""
    citations = [
        Citation(
            path="src/AuthService.java",
            start_line=10,
            end_line=20,
            score=0.95,
            reason="hybrid_rag_match",
        )
    ]
    answer = query_service._build_extractive_fallback(
        citations,
        fallback_reason="verification_failed",
    )
    assert "OpenAI no está configurado" not in answer
    assert "No se pudo validar completamente" in answer


def test_run_query_uses_inventory_short_circuit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Delegates inventory intents to graph-first inventory route."""

    def _fail_hybrid(*args, **kwargs):
        raise AssertionError("hybrid_search should not run for inventory query")

    def _fake_inventory(
        repo_id: str,
        query: str,
        page: int,
        page_size: int,
    ) -> query_service.InventoryQueryResponse:
        assert repo_id == "repo1"
        assert page == 1
        assert page_size > 0
        return query_service.InventoryQueryResponse(
            answer="inventario",
            target="modelo",
            module_name="mall-mbg",
            total=2,
            page=1,
            page_size=80,
            items=[],
            citations=[
                Citation(
                    path="mall-mbg/src/main/java/com/macro/mall/model/A.java",
                    start_line=1,
                    end_line=1,
                    score=1.0,
                    reason="inventory_graph_match",
                )
            ],
            diagnostics={"inventory_count": 2},
        )

    monkeypatch.setattr(query_service, "hybrid_search", _fail_hybrid)
    monkeypatch.setattr(query_service, "run_inventory_query", _fake_inventory)

    result = query_service.run_query(
        repo_id="repo1",
        query="cuales son todos los modelos de mall-mbg",
        top_n=80,
        top_k=20,
    )

    assert result.answer == "inventario"
    assert result.diagnostics["inventory_route"] == "graph_first"
    assert result.diagnostics["inventory_total"] == 2


def test_run_inventory_query_applies_pagination(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Returns requested page slice for inventory entities."""

    discovered = [
        {
            "label": f"Model{i}.java",
            "path": f"mall-mbg/src/main/java/com/macro/mall/model/Model{i}.java",
            "kind": "file",
            "start_line": 1,
            "end_line": 1,
        }
        for i in range(1, 6)
    ]

    monkeypatch.setattr(query_service, "_query_inventory_entities", lambda **_: discovered)

    result = query_service.run_inventory_query(
        repo_id="repo1",
        query="cuales son todos los modelos de mall-mbg",
        page=2,
        page_size=2,
    )

    assert result.total == 5
    assert result.page == 2
    assert result.page_size == 2
    assert len(result.items) == 2
    assert result.items[0].label == "Model3.java"
    assert result.items[1].label == "Model4.java"
