"""Formatting helpers for ingestion UI summaries and technical output."""

from __future__ import annotations

import json


def format_deduplication_paths(
    deduplication: dict,
    limit: int = 2,
) -> str:
    """Build a short UI summary for discarded and replaced document paths."""
    incoming = deduplication.get("incoming_batch", {})
    replaced = deduplication.get("replaced_existing", {})
    if not isinstance(incoming, dict) or not isinstance(replaced, dict):
        return "-"

    skipped_paths = incoming.get("kept_paths", [])
    replaced_paths = replaced.get("replaced_paths", [])

    fragments: list[str] = []
    if isinstance(skipped_paths, list) and skipped_paths:
        shown = ", ".join(str(path) for path in skipped_paths[:limit])
        extra = max(0, len(skipped_paths) - limit)
        suffix = f" (+{extra})" if extra else ""
        fragments.append(f"conservados: {shown}{suffix}")

    if isinstance(replaced_paths, list) and replaced_paths:
        shown = ", ".join(str(path) for path in replaced_paths[:limit])
        extra = max(0, len(replaced_paths) - limit)
        suffix = f" (+{extra})" if extra else ""
        fragments.append(f"reemplazados: {shown}{suffix}")

    return " | ".join(fragments) if fragments else "-"


def format_ingestion_result(result: dict, include_raw: bool) -> str:
    """Return a readable ingestion trace for the UI text panel."""
    lines: list[str] = []

    status = str(result.get("status", "unknown"))
    lines.append(f"Status: {status}")

    progress_pct = result.get("progress_pct")
    if isinstance(progress_pct, (int, float)):
        lines.append(f"Progress: {round(float(progress_pct), 2)}%")

    message = result.get("message")
    if isinstance(message, str) and message.strip():
        lines.append(f"Message: {message}")

    source_id = result.get("source_id")
    if isinstance(source_id, str) and source_id:
        lines.append(f"Source ID: {source_id}")

    documents = result.get("documents")
    chunks = result.get("chunks")
    if documents is not None and chunks is not None:
        lines.append(f"Documents: {documents} | Chunks: {chunks}")

    metrics = result.get("metrics")
    if isinstance(metrics, dict) and metrics:
        lines.append("\nMetrics:")
        for key, value in metrics.items():
            lines.append(f"- {key}: {value}")

    deduplication = result.get("deduplication")
    if isinstance(deduplication, dict) and deduplication:
        lines.append("\nDeduplication:")
        for section_name, section in deduplication.items():
            if not isinstance(section, dict):
                continue
            lines.append(f"- {section_name}:")
            for key, value in section.items():
                lines.append(f"  - {key}: {value}")

    steps = result.get("steps")
    if isinstance(steps, list) and steps:
        lines.append("\nIngestion Timeline:")
        timed_steps = 0
        total_elapsed = ""
        for index, step in enumerate(steps, start=1):
            if not isinstance(step, dict):
                continue
            ordinal = step.get("ordinal")
            display_index = int(ordinal) if isinstance(ordinal, int) else index
            name = str(step.get("name", "step"))
            step_status = str(step.get("status", "ok"))
            elapsed_hhmmss = step.get("elapsed_hhmmss")
            elapsed_hint = ""
            if isinstance(elapsed_hhmmss, str) and elapsed_hhmmss:
                elapsed_hint = f" ({elapsed_hhmmss})"
                timed_steps += 1
                total_elapsed = elapsed_hhmmss
            lines.append(f"{display_index}. [{step_status}] {name}{elapsed_hint}")
            details = step.get("details", {})
            if isinstance(details, dict):
                for key, value in details.items():
                    if key == "progress_pct":
                        continue
                    lines.append(f"   - {key}: {value}")

        if timed_steps > 0:
            lines.append("\nProgress Summary:")
            lines.append(f"- total_elapsed_hhmmss: {total_elapsed}")
            lines.append(f"- recorded_steps: {timed_steps}")

    if include_raw:
        lines.append("\nRaw JSON:")
        lines.append(json.dumps(result, indent=2, ensure_ascii=False))
    return "\n".join(lines)


def format_async_readiness(payload: dict) -> str:
    """Format readiness payload for operator-facing technical output."""
    checks = payload.get("checks") if isinstance(payload, dict) else None
    lines = ["Readiness de ingesta asincrona:"]
    lines.append(f"- ready: {payload.get('ready')}")
    lines.append(f"- recommendation: {payload.get('recommendation', 'sync')}")
    if isinstance(checks, dict):
        for name, value in checks.items():
            if not isinstance(value, dict):
                continue
            line_parts = [
                f"{name}: ok={value.get('ok')}",
                f"required={value.get('required')}",
            ]

            signal = str(value.get("signal") or "").strip()
            if signal:
                line_parts.append(f"signal={signal}")

            mode = str(value.get("mode") or "").strip()
            if mode:
                line_parts.append(f"mode={mode}")

            target = str(value.get("target") or "").strip()
            persist_dir = str(value.get("persist_dir") or "").strip()
            if target:
                line_parts.append(f"target={target}")
            elif persist_dir:
                line_parts.append(f"persist_dir={persist_dir}")

            auth_mode = str(value.get("auth_mode") or "").strip()
            if auth_mode:
                line_parts.append(f"auth={auth_mode}")

            collection = str(value.get("collection") or "").strip()
            if collection:
                line_parts.append(f"collection={collection}")

            collections_count = value.get("collections_count")
            if isinstance(collections_count, int):
                line_parts.append(f"collections={collections_count}")

            heartbeat_ok = value.get("heartbeat_ok")
            if isinstance(heartbeat_ok, bool):
                line_parts.append(f"heartbeat_ok={heartbeat_ok}")

            hnsw_space = str(value.get("hnsw_space") or "").strip()
            if hnsw_space:
                line_parts.append(f"hnsw={hnsw_space}")

            expected_hnsw_space = str(value.get("expected_hnsw_space") or "").strip()
            if expected_hnsw_space:
                line_parts.append(f"expected_hnsw={expected_hnsw_space}")

            indexed = value.get("indexed")
            if isinstance(indexed, bool):
                line_parts.append(f"indexed={indexed}")

            corpus_rows = value.get("corpus_rows")
            if isinstance(corpus_rows, int):
                line_parts.append(f"corpus_rows={corpus_rows}")

            document_count = value.get("document_count")
            if isinstance(document_count, int):
                line_parts.append(f"documents={document_count}")

            source_count = value.get("source_count")
            if isinstance(source_count, int):
                line_parts.append(f"sources={source_count}")

            line_parts.append(f"detail={value.get('detail', '')}")
            lines.append("- " + " ".join(line_parts))
    return "\n".join(lines)


def localize_status(status: str) -> str:
    """Map backend status values to UI-friendly Spanish labels."""
    normalized = status.strip().lower()
    mapping = {
        "queued": "en cola",
        "running": "en curso",
        "started": "en curso",
        "completed": "completado",
        "finished": "completado",
        "failed": "fallido",
        "idle": "inactivo",
    }
    return mapping.get(normalized, normalized or "desconocido")


def status_to_badge(status: object) -> str:
    """Map backend status string to known badge tokens."""
    normalized = str(status or "").strip().lower()
    if normalized in {"completed", "finished"}:
        return "success"
    if normalized == "failed":
        return "error"
    if normalized in {"queued", "running", "started"}:
        return "running"
    return "idle"