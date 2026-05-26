"""HTTP client helpers for desktop UI backend interactions."""

from __future__ import annotations

import json
import mimetypes
import re
import time
from collections.abc import Callable
from contextlib import ExitStack
from copy import deepcopy
from pathlib import Path
from urllib.parse import quote

import requests
from requests import Response

from coderag.ingestion.repo_scanner import ALLOWED_EXTENSIONS


def _parse_upload_paths(local_path_raw: str) -> list[Path]:
    """Parse one or more local file paths from upload input text."""
    chunks = [item.strip() for item in re.split(r"[;\n]+", local_path_raw)]
    return [Path(item).expanduser() for item in chunks if item]


def _collect_upload_entries(local_path_raw: str) -> list[tuple[Path, str]]:
    """Expand local paths into upload entries with stable logical names."""
    collected: list[tuple[Path, str]] = []
    seen: set[str] = set()

    for raw_path in _parse_upload_paths(local_path_raw):
        resolved = raw_path
        if not resolved.is_absolute():
            resolved = (Path.cwd() / resolved).resolve(strict=False)

        if not resolved.exists():
            raise FileNotFoundError(f"Upload path does not exist: {resolved}")

        if resolved.is_dir():
            root_label = resolved.name.strip() or "upload"
            supported_files = [
                candidate
                for candidate in sorted(resolved.rglob("*"))
                if candidate.is_file()
                and candidate.suffix.lower() in ALLOWED_EXTENSIONS
            ]
            for candidate in supported_files:
                key = str(candidate.resolve(strict=False)).casefold()
                if key in seen:
                    continue
                seen.add(key)
                relative_name = candidate.relative_to(resolved).as_posix()
                collected.append((candidate, f"{root_label}/{relative_name}"))
            continue

        if not resolved.is_file():
            raise ValueError(f"Upload path is not a regular file: {resolved}")

        if resolved.suffix.lower() not in ALLOWED_EXTENSIONS:
            allowed = ", ".join(sorted(ALLOWED_EXTENSIONS))
            raise ValueError(
                "Unsupported upload file extension. "
                f"Allowed: {allowed}"
            )

        key = str(resolved.resolve(strict=False)).casefold()
        if key in seen:
            continue
        seen.add(key)
        collected.append((resolved, resolved.name))

    if not collected:
        allowed = ", ".join(sorted(ALLOWED_EXTENSIONS))
        raise ValueError(
            "No supported files found in the selected paths. "
            f"Allowed: {allowed}"
        )

    return collected


class UiApiClient:
    """Reusable HTTP client for desktop backend interactions."""

    def __init__(self, api_base_url: str = "http://127.0.0.1:8000") -> None:
        self.api_base_url = api_base_url.rstrip("/")

    def ingest(
        self,
        payload: dict[str, object],
        on_update: Callable[[dict[str, object]], None] | None = None,
    ) -> dict[str, object]:
        """Run ingestion in selected mode and poll when async is used."""
        source = payload.get("source")
        source_type = ""
        if isinstance(source, dict):
            source_type = str(source.get("source_type", "")).strip().lower()

        if source_type == "folder":
            return self._ingest_via_upload(payload, on_update=on_update)

        ingestion_channel = str(
            payload.get("_ingestion_channel", "json_folder")
        ).strip().lower()

        if ingestion_channel == "upload_file":
            return self._ingest_via_upload(payload, on_update=on_update)

        candidate_payload = dict(payload)
        execution_mode = str(
            candidate_payload.pop("_ingestion_mode", "async")
        ).strip().lower()
        if execution_mode not in {"async", "sync"}:
            execution_mode = "async"

        if execution_mode == "sync":
            return self.post_json("/sources/ingest", candidate_payload, timeout=3600)

        async_response = self.post_json(
            "/sources/ingest/async", candidate_payload, timeout=15
        )
        if "error" in async_response or "detail" in async_response:
            return async_response

        if on_update is not None:
            on_update(async_response)

        job_id = async_response.get("job_id")
        if not isinstance(job_id, str) or not job_id:
            return async_response

        poll_result = self.poll_job(
            job_id,
            timeout_seconds=3600,
            on_update=on_update,
        )
        if isinstance(poll_result, dict):
            poll_result.setdefault("job_id", job_id)
        return poll_result

    def _ingest_via_upload(
        self,
        payload: dict[str, object],
        on_update: Callable[[dict[str, object]], None] | None = None,
    ) -> dict[str, object]:
        """Run ingestion using multipart upload endpoints for local files."""
        candidate = deepcopy(payload)
        source = candidate.get("source")
        if not isinstance(source, dict):
            return {
                "status": "failed",
                "message": "Upload ingestion requires a 'source' object.",
            }

        execution_mode = str(
            candidate.pop("_ingestion_mode", "async")
        ).strip().lower()
        if execution_mode not in {"async", "sync"}:
            execution_mode = "async"

        source_type = str(source.get("source_type") or "folder").strip().lower()
        local_path_raw = source.get("local_path")
        filters_raw = source.get("filters", {})
        tags_raw = source.get("tags", [])

        if source_type != "folder":
            return {
                "status": "failed",
                "message": "Upload ingestion supports source_type 'folder' only.",
            }
        if not isinstance(local_path_raw, str) or not local_path_raw.strip():
            return {
                "status": "failed",
                "message": "Upload ingestion requires one or more local file paths.",
            }
        if not isinstance(filters_raw, dict):
            return {
                "status": "failed",
                "message": "Upload ingestion expects source.filters as JSON object.",
            }
        if not isinstance(tags_raw, list):
            return {
                "status": "failed",
                "message": "Upload ingestion expects source.tags as list.",
            }

        try:
            upload_entries = _collect_upload_entries(local_path_raw)
        except (ValueError, FileNotFoundError, OSError) as exc:
            return {
                "status": "failed",
                "message": str(exc),
            }

        if on_update is not None:
            on_update(
                {
                    "status": "running",
                    "message": "Enumerating local files for multipart upload.",
                    "progress_pct": 2.0,
                    "step": {
                        "name": "local_file_enumeration_completed",
                        "status": "ok",
                        "details": {"file_count": len(upload_entries)},
                    },
                    "steps": [
                        {
                            "name": "local_file_enumeration_completed",
                            "status": "ok",
                            "details": {"file_count": len(upload_entries)},
                        }
                    ],
                }
            )

        endpoint = "/sources/ingest/files"
        timeout = 3600
        if execution_mode == "async":
            endpoint = "/sources/ingest/files/async"
            timeout = 15

        response = self.post_multipart(
            endpoint,
            upload_entries=upload_entries,
            source_type=source_type,
            filters=filters_raw,
            tags=[str(tag) for tag in tags_raw],
            timeout=timeout,
        )
        if execution_mode == "sync":
            return response
        if "error" in response or "detail" in response:
            return response

        if on_update is not None:
            on_update(response)

        job_id = response.get("job_id")
        if not isinstance(job_id, str) or not job_id:
            return response

        poll_result = self.poll_job(
            job_id,
            timeout_seconds=3600,
            on_update=on_update,
        )
        if isinstance(poll_result, dict):
            poll_result.setdefault("job_id", job_id)
        return poll_result

    def ingest_readiness(self) -> dict[str, object]:
        """Fetch operational readiness details for async ingestion mode."""
        return self.get_json("/sources/ingest/readiness", timeout=10)

    def query(self, payload: dict[str, object]) -> dict[str, object]:
        """Call backend query endpoint."""
        return self.post_json("/query", payload, timeout=180)

    def list_documents(
        self,
        source_id: str | None = None,
        tags: list[str] | None = None,
    ) -> dict[str, object]:
        """Fetch ingested document catalog for optional source filter."""
        path = "/sources/documents"
        query_parts: list[str] = []
        if source_id:
            query_parts.append(f"source_id={quote(source_id, safe='')}")
        if tags:
            query_parts.append(f"tags={quote(','.join(tags), safe='')}")
        if query_parts:
            path = f"{path}?{'&'.join(query_parts)}"
        return self.get_json(path, timeout=30)

    def list_document_tags(
        self,
        source_id: str | None = None,
    ) -> dict[str, object]:
        """Fetch aggregated tag facets for optional source filter."""
        path = "/sources/tags"
        if source_id:
            path = f"{path}?source_id={quote(source_id, safe='')}"
        return self.get_json(path, timeout=30)

    def delete_document(self, document_id: str) -> dict[str, object]:
        """Delete one persisted document from the backend catalog."""
        return self.delete_json(
            f"/sources/documents/{quote(document_id, safe='')}",
            timeout=60,
        )

    def replace_document_tags(
        self,
        document_id: str,
        tags: list[str],
    ) -> dict[str, object]:
        """Replace the persisted tags for one document."""
        return self.put_json(
            f"/sources/documents/{quote(document_id, safe='')}/tags",
            {"tags": tags},
            timeout=60,
        )

    def reset_all(self) -> dict[str, object]:
        """Call backend endpoint to clear all repositories and indexes."""
        return self.delete_json(
            "/sources/reset?confirm=true",
            timeout=180,
        )

    def tdm_ingest(self, payload: dict[str, object]) -> dict[str, object]:
        """Call backend TDM ingest endpoint."""
        return self.post_json("/tdm/ingest", payload, timeout=3600)

    def tdm_query(self, payload: dict[str, object]) -> dict[str, object]:
        """Call backend TDM query endpoint."""
        return self.post_json("/tdm/query", payload, timeout=180)

    def tdm_service_catalog(
        self,
        service_name: str,
        source_id: str | None = None,
    ) -> dict[str, object]:
        """Fetch TDM service catalog by service name."""
        path = f"/tdm/catalog/services/{service_name}"
        if source_id:
            path = f"{path}?source_id={source_id}"
        return self.get_json(path, timeout=60)

    def tdm_table_catalog(
        self,
        table_name: str,
        source_id: str | None = None,
    ) -> dict[str, object]:
        """Fetch TDM table catalog by table name."""
        path = f"/tdm/catalog/tables/{table_name}"
        if source_id:
            path = f"{path}?source_id={source_id}"
        return self.get_json(path, timeout=60)

    def tdm_virtualization_preview(
        self,
        payload: dict[str, object],
    ) -> dict[str, object]:
        """Call backend TDM virtualization preview endpoint."""
        return self.post_json(
            "/tdm/virtualization/preview",
            payload,
            timeout=180,
        )

    def tdm_synthetic_profile(
        self,
        table_name: str,
        source_id: str | None = None,
        target_rows: int = 1000,
    ) -> dict[str, object]:
        """Fetch synthetic profile plan for one table."""
        path = (
            "/tdm/synthetic/profile/"
            f"{table_name}?target_rows={max(1, int(target_rows))}"
        )
        if source_id:
            path = f"{path}&source_id={source_id}"
        return self.get_json(path, timeout=120)

    def post_json(
        self,
        path: str,
        payload: dict[str, object],
        timeout: int,
    ) -> dict[str, object]:
        """Call backend POST endpoint and parse JSON response."""
        try:
            response = requests.post(
                f"{self.api_base_url}{path}",
                json=payload,
                timeout=timeout,
            )
            response.raise_for_status()
            return response.json()
        except requests.RequestException as exc:
            return self.format_request_exception(exc)

    def get_json(self, path: str, timeout: int) -> dict[str, object]:
        """Call backend GET endpoint and parse JSON response."""
        try:
            response = requests.get(f"{self.api_base_url}{path}", timeout=timeout)
            response.raise_for_status()
            return response.json()
        except requests.RequestException as exc:
            return self.format_request_exception(exc)

    def delete_json(self, path: str, timeout: int) -> dict[str, object]:
        """Call backend DELETE endpoint and parse JSON response."""
        try:
            response = requests.delete(
                f"{self.api_base_url}{path}",
                timeout=timeout,
            )
            response.raise_for_status()
            return response.json()
        except requests.RequestException as exc:
            return self.format_request_exception(exc)

    def put_json(
        self,
        path: str,
        payload: dict[str, object],
        timeout: int,
    ) -> dict[str, object]:
        """Call backend PUT endpoint and parse JSON response."""
        try:
            response = requests.put(
                f"{self.api_base_url}{path}",
                json=payload,
                timeout=timeout,
            )
            response.raise_for_status()
            return response.json()
        except requests.RequestException as exc:
            return self.format_request_exception(exc)

    def post_multipart(
        self,
        path: str,
        upload_entries: list[tuple[Path, str]],
        source_type: str,
        filters: dict[str, object],
        tags: list[str],
        timeout: int,
    ) -> dict[str, object]:
        """Call backend multipart upload endpoint and parse JSON response."""
        if not upload_entries:
            return {
                "status": "failed",
                "message": "Upload ingestion requires one or more file paths.",
            }

        try:
            with ExitStack() as stack:
                multipart_files: list[tuple[str, tuple[str, object, str]]] = []
                for file_path, logical_name in upload_entries:
                    guessed_mime, _ = mimetypes.guess_type(str(file_path))
                    mime_type = guessed_mime or "application/octet-stream"
                    file_handle = stack.enter_context(file_path.open("rb"))
                    multipart_files.append(
                        (
                            "files",
                            (
                                logical_name,
                                file_handle,
                                mime_type,
                            ),
                        )
                    )

                response = requests.post(
                    f"{self.api_base_url}{path}",
                    data={
                        "source_type": source_type,
                        "filters": json.dumps(filters, ensure_ascii=False),
                        "tags": ",".join(tags),
                    },
                    files=multipart_files,
                    timeout=timeout,
                )
            response.raise_for_status()
            return response.json()
        except requests.RequestException as exc:
            return self.format_request_exception(exc)

    def poll_job(
        self,
        job_id: str,
        timeout_seconds: int,
        on_update: Callable[[dict[str, object]], None] | None = None,
    ) -> dict[str, object]:
        """Poll async ingestion status until completion or timeout."""
        terminal_states = {"completed", "finished", "failed"}
        started = time.monotonic()

        while time.monotonic() - started < timeout_seconds:
            result = self.get_json(f"/jobs/{job_id}", timeout=30)
            status = str(result.get("status", "")).strip().lower()
            if on_update is not None:
                on_update(result)

            if status in terminal_states:
                if status == "finished":
                    result["status"] = "completed"
                return result
            if "error" in result:
                return result

            time.sleep(2)

        return {
            "job_id": job_id,
            "status": "failed",
            "message": "Ingestion job polling timed out.",
        }

    @staticmethod
    def format_request_exception(
        exc: requests.RequestException,
    ) -> dict[str, object]:
        """Normalize request errors while preserving JSON payloads."""
        response = exc.response
        if response is not None:
            parsed = UiApiClient.parse_json_response(response)
            if isinstance(parsed, dict):
                parsed.setdefault("error", str(exc))
                return parsed
        return {"error": str(exc)}

    @staticmethod
    def parse_json_response(response: Response) -> dict[str, object] | None:
        """Parse JSON response safely and return dict when possible."""
        try:
            payload = response.json()
        except ValueError:
            return None
        if isinstance(payload, dict):
            return payload
        return None