"""End-to-end query orchestration for Hybrid RAG + GraphRAG."""

from pathlib import Path
import re

from coderag.core.models import Citation, QueryResponse
from coderag.core.settings import get_settings
from coderag.ingestion.graph_builder import GraphBuilder
from coderag.llm.openai_client import AnswerClient
from coderag.retrieval.context_assembler import assemble_context
from coderag.retrieval.graph_expand import expand_with_graph
from coderag.retrieval.hybrid_search import hybrid_search
from coderag.retrieval.reranker import rerank


def _build_extractive_fallback(citations: list[Citation]) -> str:
    """Build a local evidence-only answer when LLM is unavailable."""
    if not citations:
        return "No se encontró información en el repositorio."

    lines = [
        "OpenAI no está configurado; mostrando evidencias relevantes encontradas:",
    ]
    for index, citation in enumerate(citations[:5], start=1):
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
    """Normalize inventory tokens to a singular-like form."""
    normalized = token.lower().strip(".,;:!?()[]{}")
    if normalized.endswith("ies") and len(normalized) > 3:
        return normalized[:-3] + "y"
    if normalized.endswith(("ches", "shes", "sses", "xes", "zes")):
        return normalized[:-2]
    if normalized.endswith("es") and len(normalized) > 3:
        return normalized[:-1]
    if normalized.endswith("s") and len(normalized) > 2:
        return normalized[:-1]
    return normalized


def _extract_inventory_target(query: str) -> str | None:
    """Extract target entity token from inventory-style natural language queries."""
    normalized = query.lower()

    match_es = re.search(r"todos?\s+(?:los|las)?\s*([a-z0-9_-]+)", normalized)
    if match_es:
        return _normalize_inventory_token(match_es.group(1))

    match_en = re.search(r"all\s+([a-z0-9_-]+)", normalized)
    if match_en:
        return _normalize_inventory_token(match_en.group(1))

    match_which = re.search(r"which\s+([a-z0-9_-]+)", normalized)
    if match_which:
        return _normalize_inventory_token(match_which.group(1))

    return None


def _inventory_term_aliases(target_term: str) -> list[str]:
    """Expand inventory target with plural and cross-language aliases."""
    normalized = _normalize_inventory_token(target_term)
    aliases = {normalized}

    if normalized.endswith("y") and len(normalized) > 1:
        aliases.add(f"{normalized[:-1]}ies")
    aliases.add(f"{normalized}s")
    aliases.add(f"{normalized}es")

    equivalent_groups = [
        {"service", "servicio"},
        {"controller", "controlador"},
        {"repository", "repositorio"},
        {"handler", "manejador"},
        {"model", "modelo"},
        {"entity", "entidad"},
        {"client", "cliente"},
        {"adapter", "adaptador"},
        {"gateway", "pasarela"},
    ]
    for group in equivalent_groups:
        if normalized in group:
            for token in group:
                aliases.add(token)
                aliases.add(f"{token}s")
                aliases.add(f"{token}es")
            break

    return sorted(aliases)


def _query_inventory_entities(
    repo_id: str,
    target_term: str,
    module_name: str | None,
) -> list[dict]:
    """Query inventory entities from graph using generic target term."""
    graph = GraphBuilder()
    try:
        entities_by_key: dict[tuple[str, int, int], dict] = {}
        for alias in _inventory_term_aliases(target_term):
            entities = graph.query_inventory(
                repo_id=repo_id,
                target_term=alias,
                module_name=module_name,
                limit=800,
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


def run_query(repo_id: str, query: str, top_n: int, top_k: int) -> QueryResponse:
    """Run full query pipeline and return answer with citations."""
    settings = get_settings()
    initial = hybrid_search(repo_id=repo_id, query=query, top_n=top_n)
    reranked = rerank(chunks=initial, top_k=top_k)
    graph_context = expand_with_graph(chunks=reranked)
    discovered_modules = _discover_repo_modules(repo_id) if _is_module_query(query) else []
    module_name = _extract_module_name(query)
    inventory_target = _extract_inventory_target(query) if _is_inventory_query(query) else None
    discovered_inventory: list[dict] = []
    if inventory_target:
        discovered_inventory = _query_inventory_entities(
            repo_id=repo_id,
            target_term=inventory_target,
            module_name=module_name,
        )

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
    if discovered_inventory:
        inventory_lines = [
            f"- {item.get('label')} | {item.get('path')} | "
            f"{item.get('start_line')}-{item.get('end_line')}"
            for item in discovered_inventory
        ]
        service_block = "\n".join(
            [
                f"INVENTORY[{inventory_target}]",
                *inventory_lines,
            ]
        )
        context = f"{service_block}\n\n{context}"

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
    if discovered_inventory:
        inventory_citations = [
            Citation(
                path=str(item.get("path", "unknown")),
                start_line=int(item.get("start_line", 1)),
                end_line=int(item.get("end_line", 1)),
                score=1.0,
                reason="inventory_graph_match",
            )
            for item in discovered_inventory
            if not _is_noisy_path(str(item.get("path", "")))
        ]
        citations = inventory_citations + citations

    client = AnswerClient()
    if client.enabled:
        answer = client.answer(query=query, context=context)
        valid = client.verify(answer=answer, context=context)
        if not valid:
            answer = "No se encontró información en el repositorio."
    else:
        answer = _build_extractive_fallback(citations)

    diagnostics = {
        "retrieved": len(initial),
        "reranked": len(reranked),
        "graph_nodes": len(graph_context),
        "openai_enabled": client.enabled,
        "discovered_modules": discovered_modules,
        "inventory_target": inventory_target,
        "inventory_terms": (
            _inventory_term_aliases(inventory_target) if inventory_target else []
        ),
        "inventory_count": len(discovered_inventory),
    }
    return QueryResponse(answer=answer, citations=citations, diagnostics=diagnostics)
