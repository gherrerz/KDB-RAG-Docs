"""End-to-end query orchestration for Hybrid RAG + GraphRAG."""

from collections import Counter
from pathlib import Path, PurePosixPath
import re
from time import monotonic
import unicodedata

from coderag.core.models import (
    Citation,
    InventoryItem,
    InventoryQueryResponse,
    QueryResponse,
)
from coderag.core.settings import get_settings
from coderag.ingestion.graph_builder import GraphBuilder
from coderag.llm.openai_client import AnswerClient
from coderag.retrieval.context_assembler import assemble_context
from coderag.retrieval.graph_expand import expand_with_graph
from coderag.retrieval.hybrid_search import hybrid_search
from coderag.retrieval.reranker import rerank


INVENTORY_EQUIVALENT_GROUPS = [
    {"service", "servicio"},
    {"controller", "controlador"},
    {"repository", "repositorio", "repo"},
    {"handler", "manejador"},
    {"model", "modelo"},
    {"entity", "entidad"},
    {"client", "cliente"},
    {"adapter", "adaptador"},
    {"gateway", "pasarela"},
    {"dao", "dataaccess", "data-access"},
    {"config", "configuration", "configuracion", "configuración"},
    {"implementation", "implementacion", "implementación", "impl"},
    {"manager", "gestor"},
    {"factory", "fabrica", "fábrica"},
    {"helper", "util", "utils", "utilidad"},
]


def _fallback_header(fallback_reason: str) -> str:
    """Return fallback header message based on root cause."""
    messages = {
        "not_configured": (
            "OpenAI no está configurado; respuesta extractiva basada en "
            "evidencia."
        ),
        "verification_failed": (
            "No se pudo validar completamente la respuesta generada; "
            "mostrando evidencia trazable."
        ),
        "generation_error": (
            "Ocurrió un error al generar respuesta con OpenAI; mostrando "
            "evidencia trazable."
        ),
        "time_budget_exhausted": (
            "Se alcanzó el presupuesto de tiempo de consulta; mostrando "
            "evidencia trazable disponible."
        ),
    }
    return messages.get(
        fallback_reason,
        "Mostrando evidencia trazable del repositorio.",
    )


def _build_extractive_fallback(
    citations: list[Citation],
    inventory_mode: bool = False,
    inventory_target: str | None = None,
    query: str = "",
    fallback_reason: str = "not_configured",
) -> str:
    """Build a local evidence-only answer when LLM is unavailable."""
    if not citations:
        return "No se encontró información en el repositorio."

    if inventory_mode:
        unique_citations = _deduplicate_citations_by_path(citations)
        file_paths = [item.path for item in unique_citations]
        component_names = [PurePosixPath(path).name for path in file_paths]

        folders = [
            str(PurePosixPath(path).parent)
            for path in file_paths
            if str(PurePosixPath(path).parent) not in {"", "."}
        ]
        folder_counter = Counter(folders)
        top_folders = [
            folder for folder, _count in folder_counter.most_common(3)
        ]

        target_label = inventory_target or "componentes"
        lines = [
            _fallback_header(fallback_reason),
            "1) Respuesta principal:",
            (
                f"Se identificaron {len(unique_citations)} elementos para "
                f"'{target_label}' en el repositorio consultado."
            ),
            "",
            "2) Componentes/archivos clave:",
        ]
        lines.extend(f"- {name}" for name in component_names)

        if top_folders:
            lines.extend([
                "",
                "3) Organización observada en el contexto:",
            ])
            lines.extend(f"- {folder}" for folder in top_folders)

        lines.extend([
            "",
            "4) Citas de archivos con líneas:",
        ])
        lines.extend(
            (
                f"- {citation.path} "
                f"(líneas {citation.start_line}-{citation.end_line}, "
                f"score {citation.score:.4f})"
            )
            for citation in unique_citations
        )

        if query.strip():
            lines.extend([
                "",
                f"Consulta original: {query.strip()}",
            ])
        return "\n".join(lines)

    lines = [
        _fallback_header(fallback_reason),
    ]
    limit = len(citations) if inventory_mode else 5
    for index, citation in enumerate(citations[:limit], start=1):
        lines.append(
            (
                f"{index}. {citation.path} "
                f"(líneas {citation.start_line}-{citation.end_line}, "
                f"score {citation.score:.4f})"
            )
        )
    return "\n".join(lines)


def _is_module_query(query: str) -> bool:
    """Return whether user asks about repository modules/services."""
    normalized = query.lower()
    return any(
        token in normalized
        for token in ["modulo", "módulo", "module", "modulos", "módulos"]
    )


def _discover_repo_modules(repo_id: str) -> list[str]:
    """Discover top-level module folders from locally cloned repository."""
    settings = get_settings()
    repo_path = settings.workspace_path / repo_id
    if not repo_path.exists() or not repo_path.is_dir():
        return []

    excluded_names = {
        ".git",
        ".github",
        ".vscode",
        "docs",
        "doc",
        "test",
        "tests",
        "node_modules",
        "venv",
        ".venv",
        "__pycache__",
        "dist",
        "build",
        "target",
        "scripts",
    }

    modules: list[str] = []
    for child in sorted(repo_path.iterdir()):
        if not child.is_dir():
            continue
        name = child.name
        if name.startswith("."):
            continue
        if name.lower() in excluded_names:
            continue
        modules.append(name)
    return modules


def _is_inventory_query(query: str) -> bool:
    """Return whether query asks for an exhaustive list of entities."""
    normalized = query.lower()
    has_all_word = any(
        token in normalized
        for token in ["todos", "todas", "all", "lista", "listar", "cuales son"]
    )
    return has_all_word


def _extract_module_name(query: str) -> str | None:
    """Extract module or package token from natural language query."""
    normalized = query.lower()

    quoted = re.search(r"['\"]([a-z0-9_./-]+)['\"]", normalized)
    if quoted:
        return quoted.group(1)

    patterns = [
        r"(?:modulo|módulo|module|package|servicio|service)\s+([a-z0-9_./-]+)",
        r"(?:in|en|de|del|of|for)\s+([a-z0-9_./-]+)",
    ]
    for pattern in patterns:
        match = re.search(pattern, normalized)
        if match:
            token = match.group(1).strip(".,;:!?()[]{}")
            if token and token not in {"el", "la", "los", "las", "the", "a", "an"}:
                return token

    module_like = re.search(r"\b([a-z0-9]+(?:[-_/][a-z0-9]+)+)\b", normalized)
    if module_like:
        return module_like.group(1)
    return None


def _normalize_inventory_token(token: str) -> str:
    """Normalize inventory token by lowercasing and removing accents/punctuation."""
    lowered = token.lower().strip(".,;:!?()[]{}")
    decomposed = unicodedata.normalize("NFD", lowered)
    return "".join(char for char in decomposed if unicodedata.category(char) != "Mn")


def _inventory_base_forms(token: str) -> set[str]:
    """Build candidate base forms from plural/singular variants."""
    normalized = _normalize_inventory_token(token)
    forms = {normalized}

    if normalized.endswith("ies") and len(normalized) > 3:
        forms.add(normalized[:-3] + "y")

    if normalized.endswith("es") and len(normalized) > 3:
        es_root = normalized[:-2]
        if normalized.endswith(
            (
                "ses",
                "xes",
                "zes",
                "ches",
                "shes",
                "ores",
                "dores",
                "tores",
                "ciones",
                "siones",
                "ades",
                "udes",
            )
        ):
            forms.add(es_root)

    if normalized.endswith("s") and len(normalized) > 2:
        forms.add(normalized[:-1])

    return {form for form in forms if form}


def _canonical_inventory_term(token: str) -> str:
    """Return canonical inventory term from available base forms."""
    forms = _inventory_base_forms(token)
    known_terms = {
        term
        for group in INVENTORY_EQUIVALENT_GROUPS
        for term in group
    }
    for form in sorted(forms, key=lambda item: (len(item), item)):
        if form in known_terms:
            return form
    return _normalize_inventory_token(token)


def _plural_variants(token: str) -> set[str]:
    """Generate plural/surface variants for a normalized inventory term."""
    variants = {token}
    if not token:
        return variants

    if token.endswith(("s", "x", "z", "ch", "sh", "or", "ion", "dad", "dor")):
        variants.add(f"{token}es")
    else:
        variants.add(f"{token}s")
    if token.endswith("y") and len(token) > 1:
        variants.add(f"{token[:-1]}ies")
    return variants


def _deduplicate_citations(citations: list[Citation]) -> list[Citation]:
    """Deduplicate citations keeping first occurrence order."""
    seen: set[tuple[str, int, int]] = set()
    deduplicated: list[Citation] = []
    for citation in citations:
        key = (
            citation.path,
            citation.start_line,
            citation.end_line,
        )
        if key in seen:
            continue
        seen.add(key)
        deduplicated.append(citation)
    return deduplicated


def _deduplicate_citations_by_path(citations: list[Citation]) -> list[Citation]:
    """Deduplicate citations by path keeping first occurrence order."""
    seen_paths: set[str] = set()
    deduplicated: list[Citation] = []
    for citation in citations:
        key = citation.path.strip().lower()
        if key in seen_paths:
            continue
        seen_paths.add(key)
        deduplicated.append(citation)
    return deduplicated


def _extract_inventory_target(query: str) -> str | None:
    """Extract target entity token from inventory-style natural language queries."""
    normalized = query.lower()

    match_es = re.search(r"todos?\s+(?:los|las)?\s*([a-z0-9_-]+)", normalized)
    if match_es:
        return _canonical_inventory_term(match_es.group(1))

    match_en = re.search(r"all\s+([a-z0-9_-]+)", normalized)
    if match_en:
        return _canonical_inventory_term(match_en.group(1))

    match_which = re.search(r"which\s+([a-z0-9_-]+)", normalized)
    if match_which:
        return _canonical_inventory_term(match_which.group(1))

    return None


def _inventory_term_aliases(target_term: str) -> list[str]:
    """Expand inventory target with plural and cross-language aliases."""
    base_forms = _inventory_base_forms(target_term)
    aliases: set[str] = set()
    for form in base_forms:
        aliases.update(_plural_variants(form))

    for group in INVENTORY_EQUIVALENT_GROUPS:
        if base_forms.intersection(group):
            for token in group:
                normalized = _normalize_inventory_token(token)
                aliases.update(_plural_variants(normalized))

    return sorted(aliases)


def _query_inventory_entities(
    repo_id: str,
    target_term: str,
    module_name: str | None,
) -> list[dict]:
    """Query inventory entities from graph using generic target term."""
    settings = get_settings()
    graph = GraphBuilder()
    try:
        entities_by_key: dict[tuple[str, int, int], dict] = {}
        aliases = _inventory_term_aliases(target_term)[: settings.inventory_alias_limit]
        for alias in aliases:
            entities = graph.query_inventory(
                repo_id=repo_id,
                target_term=alias,
                module_name=module_name,
                limit=settings.inventory_entity_limit,
            )
            for item in entities:
                path = str(item.get("path", ""))
                start_line = int(item.get("start_line", 1))
                end_line = int(item.get("end_line", 1))
                key = (path, start_line, end_line)
                if key not in entities_by_key:
                    entities_by_key[key] = item
        return sorted(entities_by_key.values(), key=lambda item: item.get("path", ""))
    except Exception:
        return []
    finally:
        graph.close()


def _sanitize_inventory_pagination(page: int, page_size: int) -> tuple[int, int]:
    """Normalize inventory pagination arguments against configured limits."""
    settings = get_settings()
    safe_page = max(1, int(page))
    default_size = max(1, settings.inventory_page_size)
    requested_size = int(page_size) if int(page_size) > 0 else default_size
    safe_page_size = min(max(1, requested_size), settings.inventory_max_page_size)
    return safe_page, safe_page_size


def _remaining_budget_seconds(started_at: float, budget_seconds: float) -> float:
    """Return remaining budget (seconds) for a running query pipeline."""
    elapsed = monotonic() - started_at
    return max(0.0, budget_seconds - elapsed)


def _elapsed_milliseconds(started_at: float) -> float:
    """Return elapsed milliseconds rounded for diagnostics readability."""
    return round((monotonic() - started_at) * 1000, 2)


def _is_noisy_path(path: str) -> bool:
    """Return whether citation path is likely non-informative noise."""
    normalized = path.strip().lower()
    if not normalized:
        return True
    if normalized in {".", "..", "document", "docs"}:
        return True
    if normalized.startswith("document/"):
        return True
    return False


def _citation_priority(citation: Citation) -> tuple[int, float]:
    """Assign sorting priority using generic path quality signals."""
    path = citation.path.strip().lower()
    suffix = Path(path).suffix
    code_like_suffixes = {
        ".py", ".js", ".ts", ".tsx", ".jsx", ".java", ".kt", ".go",
        ".rs", ".cs", ".cpp", ".cc", ".c", ".h", ".hpp", ".php",
        ".rb", ".swift", ".scala", ".sql", ".sh", ".ps1", ".yaml",
        ".yml", ".json", ".toml", ".md", ".xml",
    }
    if suffix in code_like_suffixes:
        rank = 0
    elif "/" in path or "\\" in path:
        rank = 1
    elif path:
        rank = 2
    else:
        rank = 3
    return (rank, -citation.score)


def run_inventory_query(
    repo_id: str,
    query: str,
    page: int,
    page_size: int,
) -> InventoryQueryResponse:
    """Run graph-first inventory query with pagination and time budget."""
    settings = get_settings()
    budget_seconds = max(1.0, float(settings.query_max_seconds))
    pipeline_started_at = monotonic()
    stage_timings: dict[str, float] = {}

    parse_started_at = monotonic()
    inventory_target = _extract_inventory_target(query) if _is_inventory_query(query) else None
    module_name = _extract_module_name(query)
    inventory_terms = _inventory_term_aliases(inventory_target) if inventory_target else []
    safe_page, safe_page_size = _sanitize_inventory_pagination(page, page_size)
    stage_timings["parse_ms"] = _elapsed_milliseconds(parse_started_at)

    if not inventory_target:
        diagnostics = {
            "inventory_target": None,
            "inventory_terms": [],
            "inventory_count": 0,
            "query_budget_seconds": budget_seconds,
            "budget_exhausted": False,
            "stage_timings_ms": stage_timings,
            "fallback_reason": "inventory_target_missing",
        }
        return InventoryQueryResponse(
            answer="No se detectó un objetivo de inventario en la consulta.",
            target=None,
            module_name=module_name,
            total=0,
            page=safe_page,
            page_size=safe_page_size,
            items=[],
            citations=[],
            diagnostics=diagnostics,
        )

    fallback_reason: str | None = None
    discovered_inventory: list[dict] = []

    if _remaining_budget_seconds(pipeline_started_at, budget_seconds) <= 0:
        fallback_reason = "time_budget_exhausted"
    else:
        graph_started_at = monotonic()
        discovered_inventory = _query_inventory_entities(
            repo_id=repo_id,
            target_term=inventory_target,
            module_name=module_name,
        )
        stage_timings["graph_inventory_ms"] = _elapsed_milliseconds(graph_started_at)

    pagination_started_at = monotonic()
    total_items = len(discovered_inventory)
    offset = (safe_page - 1) * safe_page_size
    paged_inventory = discovered_inventory[offset:offset + safe_page_size]
    stage_timings["pagination_ms"] = _elapsed_milliseconds(pagination_started_at)

    items = [
        InventoryItem(
            label=str(item.get("label", "")),
            path=str(item.get("path", "unknown")),
            kind=str(item.get("kind", "file")),
            start_line=int(item.get("start_line", 1)),
            end_line=int(item.get("end_line", 1)),
        )
        for item in paged_inventory
    ]

    citations = [
        Citation(
            path=item.path,
            start_line=item.start_line,
            end_line=item.end_line,
            score=1.0,
            reason="inventory_graph_match",
        )
        for item in items
        if not _is_noisy_path(item.path)
    ]

    if (
        fallback_reason is None
        and _remaining_budget_seconds(pipeline_started_at, budget_seconds) <= 0
    ):
        fallback_reason = "time_budget_exhausted"

    answer = _build_extractive_fallback(
        citations,
        inventory_mode=True,
        inventory_target=inventory_target,
        query=query,
        fallback_reason=fallback_reason or "inventory_structured",
    )

    stage_timings["total_ms"] = _elapsed_milliseconds(pipeline_started_at)
    diagnostics = {
        "inventory_target": inventory_target,
        "inventory_terms": inventory_terms,
        "inventory_count": total_items,
        "query_budget_seconds": budget_seconds,
        "budget_exhausted": _remaining_budget_seconds(pipeline_started_at, budget_seconds) <= 0,
        "stage_timings_ms": stage_timings,
        "fallback_reason": fallback_reason,
    }

    return InventoryQueryResponse(
        answer=answer,
        target=inventory_target,
        module_name=module_name,
        total=total_items,
        page=safe_page,
        page_size=safe_page_size,
        items=items,
        citations=citations,
        diagnostics=diagnostics,
    )


def run_query(repo_id: str, query: str, top_n: int, top_k: int) -> QueryResponse:
    """Run full query pipeline and return answer with citations."""
    settings = get_settings()
    if _is_inventory_query(query):
        inventory_response = run_inventory_query(
            repo_id=repo_id,
            query=query,
            page=1,
            page_size=settings.inventory_page_size,
        )
        diagnostics = dict(inventory_response.diagnostics)
        diagnostics.update(
            {
                "inventory_route": "graph_first",
                "inventory_page": inventory_response.page,
                "inventory_page_size": inventory_response.page_size,
                "inventory_total": inventory_response.total,
            }
        )
        return QueryResponse(
            answer=inventory_response.answer,
            citations=inventory_response.citations,
            diagnostics=diagnostics,
        )

    budget_seconds = max(1.0, float(settings.query_max_seconds))
    pipeline_started_at = monotonic()
    stage_timings: dict[str, float] = {}

    retrieval_started_at = monotonic()
    initial = hybrid_search(repo_id=repo_id, query=query, top_n=top_n)
    stage_timings["hybrid_search_ms"] = _elapsed_milliseconds(retrieval_started_at)

    rerank_started_at = monotonic()
    reranked = rerank(chunks=initial, top_k=top_k)
    stage_timings["rerank_ms"] = _elapsed_milliseconds(rerank_started_at)

    graph_started_at = monotonic()
    graph_context = expand_with_graph(chunks=reranked)
    stage_timings["graph_expand_ms"] = _elapsed_milliseconds(graph_started_at)

    module_started_at = monotonic()
    discovered_modules = _discover_repo_modules(repo_id) if _is_module_query(query) else []
    stage_timings["module_discovery_ms"] = _elapsed_milliseconds(module_started_at)

    context_started_at = monotonic()
    context = assemble_context(
        chunks=reranked,
        graph_records=graph_context,
        max_tokens=settings.max_context_tokens,
    )
    if discovered_modules:
        module_block = "\n".join(
            [
                "MODULE_INVENTORY:",
                *[f"- {module}" for module in discovered_modules],
            ]
        )
        context = f"{module_block}\n\n{context}"
    stage_timings["context_assembly_ms"] = _elapsed_milliseconds(context_started_at)

    raw_citations = [
        Citation(
            path=item.metadata.get("path", "unknown"),
            start_line=int(item.metadata.get("start_line", 0)),
            end_line=int(item.metadata.get("end_line", 0)),
            score=float(item.score),
            reason="hybrid_rag_match",
        )
        for item in reranked
    ]

    filtered_citations = [
        item for item in raw_citations if not _is_noisy_path(item.path)
    ]
    citations = sorted(filtered_citations, key=_citation_priority)

    client = AnswerClient()
    fallback_reason: str | None = None
    verify_valid: bool | None = None
    verify_skipped = False
    llm_error: str | None = None

    if client.enabled and _remaining_budget_seconds(pipeline_started_at, budget_seconds) > 0:
        try:
            answer_started_at = monotonic()
            answer_timeout = min(
                float(settings.openai_timeout_seconds),
                _remaining_budget_seconds(pipeline_started_at, budget_seconds),
            )
            if answer_timeout <= 0:
                fallback_reason = "time_budget_exhausted"
                answer = _build_extractive_fallback(
                    citations,
                    query=query,
                    fallback_reason=fallback_reason,
                )
            else:
                answer = client.answer(
                    query=query,
                    context=context,
                    timeout_seconds=answer_timeout,
                )
                stage_timings["llm_answer_ms"] = _elapsed_milliseconds(answer_started_at)

                verify_timeout = min(
                    float(settings.openai_timeout_seconds),
                    _remaining_budget_seconds(pipeline_started_at, budget_seconds),
                )
                if verify_timeout <= 0:
                    verify_skipped = True
                else:
                    verify_started_at = monotonic()
                    verify_valid = client.verify(
                        answer=answer,
                        context=context,
                        timeout_seconds=verify_timeout,
                    )
                    stage_timings["llm_verify_ms"] = _elapsed_milliseconds(verify_started_at)
                    if not verify_valid:
                        fallback_reason = "verification_failed"
                        answer = _build_extractive_fallback(
                            citations,
                            query=query,
                            fallback_reason=fallback_reason,
                        )
        except Exception as exc:
            fallback_reason = "generation_error"
            llm_error = str(exc)
            answer = _build_extractive_fallback(
                citations,
                query=query,
                fallback_reason=fallback_reason,
            )
    else:
        if not client.enabled:
            fallback_reason = "not_configured"
        else:
            fallback_reason = "time_budget_exhausted"
        answer = _build_extractive_fallback(
            citations,
            query=query,
            fallback_reason=fallback_reason,
        )

    stage_timings["total_ms"] = _elapsed_milliseconds(pipeline_started_at)
    diagnostics = {
        "retrieved": len(initial),
        "reranked": len(reranked),
        "graph_nodes": len(graph_context),
        "openai_enabled": client.enabled,
        "discovered_modules": discovered_modules,
        "inventory_target": None,
        "inventory_terms": [],
        "inventory_count": 0,
        "fallback_reason": fallback_reason,
        "verify_valid": verify_valid,
        "verify_skipped": verify_skipped,
        "query_budget_seconds": budget_seconds,
        "budget_exhausted": _remaining_budget_seconds(pipeline_started_at, budget_seconds) <= 0,
        "stage_timings_ms": stage_timings,
    }
    if llm_error is not None:
        diagnostics["llm_error"] = llm_error
    return QueryResponse(answer=answer, citations=citations, diagnostics=diagnostics)
