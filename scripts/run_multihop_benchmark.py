"""Run repeatable multi-hop benchmark against indexed corpus.

This utility executes realistic complex queries through the same service
pipeline used by API/UI and reports document-diversity diagnostics.
"""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple


def _normalize_for_match(value: str) -> str:
    """Normalize text for resilient term matching across accents/case."""
    import unicodedata

    decomposed = unicodedata.normalize("NFKD", value)
    no_marks = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    return no_marks.casefold()


@dataclass(frozen=True)
class BenchmarkCase:
    """Single benchmark query definition."""

    case_id: str
    question: str
    question_type: str
    hops: int
    source_id: Optional[str]
    min_retrieval_unique_documents: int
    min_reranked_unique_documents: int
    min_citation_unique_documents: int
    min_graph_paths: int
    required_answer_terms: Tuple[str, ...]
    min_required_answer_terms_hit: int


@dataclass(frozen=True)
class BenchmarkResult:
    """Normalized benchmark execution result for one query."""

    case_id: str
    question: str
    question_type: str
    source_id: Optional[str]
    hops: int
    retrieval_candidates: int
    retrieval_unique_documents: int
    reranked_unique_documents: int
    citation_unique_documents: int
    graph_paths: int
    required_answer_terms_hit: int
    required_answer_terms_total: int
    thresholds: Dict[str, int]
    failure_reasons: List[str]
    passed: bool


def _repo_root() -> Path:
    """Return repository root based on script location."""
    return Path(__file__).resolve().parents[1]


def _bootstrap_src_path() -> None:
    """Ensure local src package layout is importable from this script."""
    repo_root = _repo_root()
    src_dir = repo_root / "src"
    src_path = str(src_dir)
    if src_dir.exists() and src_path not in sys.path:
        sys.path.insert(0, src_path)


os.chdir(_repo_root())
_bootstrap_src_path()

from coderag.core.models import QueryRequest, QueryResponse
from coderag.core.service import SERVICE


def _default_source_id(repo_root: Path) -> Optional[str]:
    """Return source_id with most documents from local metadata store."""
    db_path = repo_root / "storage" / "metadata.db"
    if not db_path.exists():
        return None

    with sqlite3.connect(db_path) as connection:
        cursor = connection.cursor()
        row = cursor.execute(
            """
            SELECT source_id, COUNT(*) AS doc_count
            FROM documents
            GROUP BY source_id
            ORDER BY doc_count DESC, source_id ASC
            LIMIT 1
            """
        ).fetchone()
    if not row:
        return None
    return str(row[0])


def _load_cases(path: Path) -> List[BenchmarkCase]:
    """Load benchmark cases from JSON file and validate structure."""
    data = json.loads(path.read_text(encoding="utf-8"))

    thresholds_by_type: Dict[str, Dict[str, int]] = {}
    raw_cases: Any
    if isinstance(data, list):
        raw_cases = data
    elif isinstance(data, dict):
        raw_cases = data.get("cases", [])
        raw_thresholds = data.get("thresholds_by_type", {})
        if not isinstance(raw_thresholds, dict):
            raise ValueError("'thresholds_by_type' must be an object.")
        thresholds_by_type = {
            str(key): {
                str(metric): max(0, int(value))
                for metric, value in values.items()
                if isinstance(values, dict)
            }
            for key, values in raw_thresholds.items()
        }
    else:
        raise ValueError(
            "Benchmark file must contain either a JSON array or an object "
            "with 'cases'."
        )

    if not isinstance(raw_cases, list):
        raise ValueError("Benchmark cases must be a JSON array.")

    default_thresholds = thresholds_by_type.get("default", {})

    def _resolve_thresholds(
        item: Dict[str, Any],
        question_type: str,
    ) -> Tuple[int, int, int, int, int]:
        base = dict(default_thresholds)
        base.update(thresholds_by_type.get(question_type, {}))

        min_retrieval_unique_documents = int(
            item.get(
                "min_retrieval_unique_documents",
                base.get("min_retrieval_unique_documents", 1),
            )
        )
        min_reranked_unique_documents = int(
            item.get(
                "min_reranked_unique_documents",
                base.get("min_reranked_unique_documents", 2),
            )
        )
        min_citation_unique_documents = int(
            item.get(
                "min_citation_unique_documents",
                base.get("min_citation_unique_documents", 2),
            )
        )
        min_graph_paths = int(
            item.get("min_graph_paths", base.get("min_graph_paths", 0))
        )
        min_required_answer_terms_hit = int(
            item.get(
                "min_required_answer_terms_hit",
                base.get("min_required_answer_terms_hit", 0),
            )
        )

        return (
            max(1, min_retrieval_unique_documents),
            max(1, min_reranked_unique_documents),
            max(1, min_citation_unique_documents),
            max(0, min_graph_paths),
            max(0, min_required_answer_terms_hit),
        )

    cases: List[BenchmarkCase] = []
    for item in raw_cases:
        if not isinstance(item, dict):
            raise ValueError("Each benchmark case must be a JSON object.")
        case_id = str(item.get("id", "")).strip()
        question = str(item.get("question", "")).strip()
        if not case_id or not question:
            raise ValueError("Each case requires non-empty 'id' and 'question'.")

        question_type = str(item.get("type", "default")).strip() or "default"

        hops = int(item.get("hops", 2))
        source_id = item.get("source_id")
        case_source_id = str(source_id).strip() if source_id else None
        (
            min_retrieval_unique_documents,
            min_reranked_unique_documents,
            min_citation_unique_documents,
            min_graph_paths,
            min_required_answer_terms_hit,
        ) = _resolve_thresholds(item, question_type)
        raw_required_terms = item.get("required_answer_terms", [])
        required_terms = tuple(
            str(term).strip()
            for term in raw_required_terms
            if str(term).strip()
        )
        terms_threshold = min_required_answer_terms_hit
        if required_terms and terms_threshold <= 0:
            terms_threshold = len(required_terms)

        cases.append(
            BenchmarkCase(
                case_id=case_id,
                question=question,
                question_type=question_type,
                hops=max(1, hops),
                source_id=case_source_id,
                min_retrieval_unique_documents=min_retrieval_unique_documents,
                min_reranked_unique_documents=min_reranked_unique_documents,
                min_citation_unique_documents=min_citation_unique_documents,
                min_graph_paths=min_graph_paths,
                required_answer_terms=required_terms,
                min_required_answer_terms_hit=min(
                    max(0, terms_threshold), len(required_terms)
                ),
            )
        )
    return cases


def _citation_unique_documents(response: QueryResponse) -> int:
    """Count unique document ids represented in evidence citations."""
    return len({citation.document_id for citation in response.citations})


def _run_case(
    case: BenchmarkCase,
    default_source_id: Optional[str],
) -> BenchmarkResult:
    """Execute a query case through service pipeline with fallback LLM mode."""
    effective_source_id = case.source_id or default_source_id
    request = QueryRequest(
        question=case.question,
        source_id=effective_source_id,
        hops=case.hops,
        force_fallback=True,
        include_llm_answer=True,
    )
    response = SERVICE.query(request)
    diagnostics = response.diagnostics

    retrieval_candidates = int(diagnostics.get("retrieval_candidates", 0))
    retrieval_unique_documents = int(
        diagnostics.get("retrieval_unique_documents", 0)
    )
    reranked_unique_documents = int(
        diagnostics.get("reranked_unique_documents", 0)
    )
    graph_paths = int(diagnostics.get("graph_paths", 0))
    citation_unique_documents = _citation_unique_documents(response)
    answer_text = response.answer or ""
    evidence_text = "\n".join(
        " ".join(
            [
                citation.snippet or "",
                citation.section_name or "",
                citation.document_id or "",
            ]
        ).strip()
        for citation in response.citations
    )
    evaluation_text = "\n".join([answer_text, evidence_text])

    normalized_answer = _normalize_for_match(evaluation_text)
    required_answer_terms_hit = sum(
        1
        for term in case.required_answer_terms
        if _normalize_for_match(term) in normalized_answer
    )

    failure_reasons: List[str] = []
    if retrieval_unique_documents < case.min_retrieval_unique_documents:
        failure_reasons.append(
            "retrieval_unique_documents "
            f"{retrieval_unique_documents} < "
            f"{case.min_retrieval_unique_documents}"
        )
    if reranked_unique_documents < case.min_reranked_unique_documents:
        failure_reasons.append(
            "reranked_unique_documents "
            f"{reranked_unique_documents} < "
            f"{case.min_reranked_unique_documents}"
        )
    if citation_unique_documents < case.min_citation_unique_documents:
        failure_reasons.append(
            "citation_unique_documents "
            f"{citation_unique_documents} < "
            f"{case.min_citation_unique_documents}"
        )
    if graph_paths < case.min_graph_paths:
        failure_reasons.append(
            f"graph_paths {graph_paths} < {case.min_graph_paths}"
        )
    if required_answer_terms_hit < case.min_required_answer_terms_hit:
        failure_reasons.append(
            "required_answer_terms_hit "
            f"{required_answer_terms_hit} < "
            f"{case.min_required_answer_terms_hit}"
        )

    passed = not failure_reasons

    return BenchmarkResult(
        case_id=case.case_id,
        question=case.question,
        question_type=case.question_type,
        source_id=effective_source_id,
        hops=case.hops,
        retrieval_candidates=retrieval_candidates,
        retrieval_unique_documents=retrieval_unique_documents,
        reranked_unique_documents=reranked_unique_documents,
        citation_unique_documents=citation_unique_documents,
        graph_paths=graph_paths,
        required_answer_terms_hit=required_answer_terms_hit,
        required_answer_terms_total=len(case.required_answer_terms),
        thresholds={
            "min_retrieval_unique_documents": (
                case.min_retrieval_unique_documents
            ),
            "min_reranked_unique_documents": (
                case.min_reranked_unique_documents
            ),
            "min_citation_unique_documents": (
                case.min_citation_unique_documents
            ),
            "min_graph_paths": case.min_graph_paths,
            "min_required_answer_terms_hit": (
                case.min_required_answer_terms_hit
            ),
        },
        failure_reasons=failure_reasons,
        passed=passed,
    )


def _as_json_payload(results: Sequence[BenchmarkResult]) -> Dict[str, Any]:
    """Convert benchmark results to a serializable JSON payload."""
    total = len(results)
    passed = sum(1 for item in results if item.passed)
    return {
        "summary": {
            "total": total,
            "passed": passed,
            "failed": total - passed,
            "pass_rate": round((passed / total) * 100, 2) if total else 0.0,
        },
        "summary_by_type": _summary_by_type(results),
        "results": [
            {
                "id": item.case_id,
                "question": item.question,
                "type": item.question_type,
                "source_id": item.source_id,
                "hops": item.hops,
                "retrieval_candidates": item.retrieval_candidates,
                "retrieval_unique_documents": item.retrieval_unique_documents,
                "reranked_unique_documents": item.reranked_unique_documents,
                "citation_unique_documents": item.citation_unique_documents,
                "graph_paths": item.graph_paths,
                "required_answer_terms_hit": item.required_answer_terms_hit,
                "required_answer_terms_total": (
                    item.required_answer_terms_total
                ),
                "thresholds": item.thresholds,
                "failure_reasons": item.failure_reasons,
                "passed": item.passed,
            }
            for item in results
        ],
    }


def _summary_by_type(
    results: Sequence[BenchmarkResult],
) -> Dict[str, Dict[str, float]]:
    """Aggregate pass/fail counts grouped by question type."""
    grouped: Dict[str, List[BenchmarkResult]] = {}
    for item in results:
        grouped.setdefault(item.question_type, []).append(item)

    summary: Dict[str, Dict[str, float]] = {}
    for question_type, items in grouped.items():
        total = len(items)
        passed = sum(1 for item in items if item.passed)
        summary[question_type] = {
            "total": total,
            "passed": passed,
            "failed": total - passed,
            "pass_rate": round((passed / total) * 100, 2) if total else 0.0,
        }
    return summary


def _build_markdown_report(
    benchmark_file: Path,
    json_payload: Dict[str, Any],
) -> str:
    """Build markdown report to inspect benchmark runs quickly."""
    summary = json_payload["summary"]
    lines = [
        "# Multi-hop Benchmark Report",
        "",
        f"- Benchmark file: `{benchmark_file.as_posix()}`",
        f"- Total cases: {summary['total']}",
        f"- Passed: {summary['passed']}",
        f"- Failed: {summary['failed']}",
        f"- Pass rate: {summary['pass_rate']}%",
        "",
        "## Summary by type",
        "",
        "| Type | Total | Passed | Failed | Pass rate |",
        "|---|---:|---:|---:|---:|",
    ]

    for question_type, type_summary in json_payload["summary_by_type"].items():
        lines.append(
            "| {type_name} | {total} | {passed} | {failed} | {pass_rate}% |".format(
                type_name=question_type,
                total=type_summary["total"],
                passed=type_summary["passed"],
                failed=type_summary["failed"],
                pass_rate=type_summary["pass_rate"],
            )
        )

    lines.extend(
        [
            "",
            "## Case results",
            "",
            "| Case | Type | Pass | Retrieval docs | Reranked docs | Citation docs | Graph paths | Terms hit |",
            "|---|---|---|---:|---:|---:|---:|---:|",
        ]
    )

    for item in json_payload["results"]:
        pass_text = "yes" if item["passed"] else "no"
        lines.append(
            "| {id} | {type_name} | {passed} | {retrieval} | {reranked} | {citations} | {paths} | {terms_hit}/{terms_total} |".format(
                id=item["id"],
                type_name=item["type"],
                passed=pass_text,
                retrieval=item["retrieval_unique_documents"],
                reranked=item["reranked_unique_documents"],
                citations=item["citation_unique_documents"],
                paths=item["graph_paths"],
                terms_hit=item["required_answer_terms_hit"],
                terms_total=item["required_answer_terms_total"],
            )
        )

        if item["failure_reasons"]:
            lines.append(
                "  - Failure reasons: "
                + "; ".join(item["failure_reasons"])
            )

    return "\n".join(lines) + "\n"


def _print_console_summary(results: Iterable[BenchmarkResult]) -> None:
    """Print compact results directly to console for quick triage."""
    result_list = list(results)
    total = len(result_list)
    passed = sum(1 for item in result_list if item.passed)
    print(f"cases={total} passed={passed} failed={total - passed}")
    by_type = _summary_by_type(result_list)
    for question_type, summary in by_type.items():
        print(
            "type={type_name} total={total} passed={passed} failed={failed}".format(
                type_name=question_type,
                total=summary["total"],
                passed=summary["passed"],
                failed=summary["failed"],
            )
        )

    for item in result_list:
        status = "PASS" if item.passed else "FAIL"
        print(
            "{status} {case} type={type_name} retrieval_docs={retrieval} "
            "reranked_docs={reranked} citation_docs={citations} "
            "graph_paths={paths} terms_hit={terms_hit}/{terms_total}".format(
                status=status,
                case=item.case_id,
                type_name=item.question_type,
                retrieval=item.retrieval_unique_documents,
                reranked=item.reranked_unique_documents,
                citations=item.citation_unique_documents,
                paths=item.graph_paths,
                terms_hit=item.required_answer_terms_hit,
                terms_total=item.required_answer_terms_total,
            )
        )

        if item.failure_reasons:
            print("  reasons=" + " | ".join(item.failure_reasons))


def build_parser() -> argparse.ArgumentParser:
    """Build CLI parser for benchmark execution options."""
    parser = argparse.ArgumentParser(
        description=(
            "Execute complex multi-hop queries and report cross-document "
            "retrieval coverage diagnostics."
        )
    )
    parser.add_argument(
        "--benchmark-file",
        default="docs/benchmarks/complex_queries.json",
        help="Path to benchmark case file.",
    )
    parser.add_argument(
        "--source-id",
        default=None,
        help="Optional source_id override for every query.",
    )
    parser.add_argument(
        "--output-json",
        default="docs/benchmarks/last_run.json",
        help="Path to write JSON report.",
    )
    parser.add_argument(
        "--output-md",
        default="docs/benchmarks/last_run.md",
        help="Path to write Markdown report.",
    )
    parser.add_argument(
        "--fail-on-threshold",
        action="store_true",
        help="Return exit code 1 when at least one case fails.",
    )
    return parser


def main() -> int:
    """CLI entrypoint for repeatable multi-hop benchmark runs."""
    parser = build_parser()
    args = parser.parse_args()

    repo_root = _repo_root()
    benchmark_file = (repo_root / args.benchmark_file).resolve()
    output_json = (repo_root / args.output_json).resolve()
    output_md = (repo_root / args.output_md).resolve()

    cases = _load_cases(benchmark_file)
    default_source_id = args.source_id or _default_source_id(repo_root)

    if not default_source_id:
        print("No source_id available. Run ingestion first.")
        return 2

    results: List[BenchmarkResult] = []
    try:
        for case in cases:
            results.append(_run_case(case, default_source_id=default_source_id))
    finally:
        SERVICE.close()

    _print_console_summary(results)

    payload = _as_json_payload(results)
    output_json.parent.mkdir(parents=True, exist_ok=True)
    output_json.write_text(
        json.dumps(payload, ensure_ascii=True, indent=2),
        encoding="utf-8",
    )
    output_md.write_text(
        _build_markdown_report(benchmark_file, payload),
        encoding="utf-8",
    )

    if args.fail_on_threshold and any(not item.passed for item in results):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
