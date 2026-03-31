"""Main desktop window combining ingestion and query views."""

from __future__ import annotations

import sys
import time
from copy import deepcopy
from typing import Any, Callable, Dict, Optional

import requests
from requests import Response
from PySide6.QtWidgets import QApplication, QMainWindow, QTabWidget, QWidget, QVBoxLayout

from coderag.ui.ingestion_view import IngestionView
from coderag.ui.query_view import QueryView
from coderag.ui.staging import stage_folder_source
from coderag.ui.theme import build_stylesheet


def _prepare_ingestion_payload(
    payload: Dict[str, Any],
) -> tuple[Dict[str, Any], Dict[str, Any] | None]:
    """Stage folder sources locally so backend always reads repo-mounted paths."""
    candidate = deepcopy(payload)
    source = candidate.get("source")
    if not isinstance(source, dict):
        return candidate, None

    source_type = str(source.get("source_type", "")).strip().lower()
    if source_type != "folder":
        return candidate, None

    local_path = source.get("local_path")
    if not isinstance(local_path, str) or not local_path.strip():
        raise ValueError("Folder ingestion requires a local folder path.")

    staged_path, metadata = stage_folder_source(local_path)
    source["local_path"] = staged_path

    progress = {
        "status": "running",
        "message": "Folder source synced to local staging area.",
        "progress_pct": 2.0,
        "staging": metadata,
        "step": {
            "name": "local_staging_completed",
            "status": "ok",
            "details": metadata,
        },
        "steps": [
            {
                "name": "local_staging_completed",
                "status": "ok",
                "details": metadata,
            }
        ],
    }
    return candidate, progress


class MainWindow(QMainWindow):
    """Main UI shell for the RAG Hybrid Response Validator."""

    def __init__(self, api_base_url: str = "http://127.0.0.1:8000") -> None:
        super().__init__()
        self.api_base_url = api_base_url.rstrip("/")
        self.setWindowTitle("RAG Hybrid Response Validator")
        self.resize(1100, 760)

        self.setStyleSheet(build_stylesheet())

        tabs = QTabWidget()
        tabs.addTab(IngestionView(self.ingest, self.reset_all), "Ingestion")
        tabs.addTab(QueryView(self.query), "Query")

        shell = QWidget()
        shell_layout = QVBoxLayout(shell)
        shell_layout.setContentsMargins(14, 14, 14, 14)
        shell_layout.addWidget(tabs)
        self.setCentralWidget(shell)

    def ingest(
        self,
        payload: Dict[str, Any],
        on_update: Optional[Callable[[Dict[str, Any]], None]] = None,
    ) -> Dict[str, Any]:
        """Run ingestion through async endpoint and poll live progress."""
        try:
            prepared_payload, preflight_update = _prepare_ingestion_payload(payload)
        except (ValueError, FileNotFoundError, NotADirectoryError, OSError) as exc:
            return {
                "status": "failed",
                "message": str(exc),
                "progress_pct": 100.0,
                "steps": [
                    {
                        "name": "local_staging_failed",
                        "status": "failed",
                        "details": {"error": str(exc)},
                    }
                ],
            }

        if on_update is not None and preflight_update is not None:
            on_update(preflight_update)

        async_response = self._post_json(
            "/sources/ingest/async", prepared_payload, timeout=15
        )
        if "error" in async_response or "detail" in async_response:
            return async_response

        if on_update is not None:
            on_update(async_response)

        job_id = async_response.get("job_id")
        if not isinstance(job_id, str) or not job_id:
            return async_response

        poll_result = self._poll_job(
            job_id,
            timeout_seconds=3600,
            on_update=on_update,
        )
        if isinstance(poll_result, dict):
            poll_result.setdefault("job_id", job_id)
        return poll_result

    def query(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Call backend query endpoint."""
        return self._post_json("/query", payload, timeout=180)

    def reset_all(self) -> Dict[str, Any]:
        """Call backend endpoint to clear all repositories and indexes."""
        return self._post_json(
            "/sources/reset",
            {"confirm": True},
            timeout=180,
        )

    def _post_json(
        self,
        path: str,
        payload: Dict[str, Any],
        timeout: int,
    ) -> Dict[str, Any]:
        try:
            response = requests.post(
                f"{self.api_base_url}{path}",
                json=payload,
                timeout=timeout,
            )
            response.raise_for_status()
            return response.json()
        except requests.RequestException as exc:
            return self._format_request_exception(exc)

    def _get_json(self, path: str, timeout: int) -> Dict[str, Any]:
        """Call backend GET endpoint and parse JSON response."""
        try:
            response = requests.get(f"{self.api_base_url}{path}", timeout=timeout)
            response.raise_for_status()
            return response.json()
        except requests.RequestException as exc:
            return self._format_request_exception(exc)

    def _poll_job(
        self,
        job_id: str,
        timeout_seconds: int,
        on_update: Optional[Callable[[Dict[str, Any]], None]] = None,
    ) -> Dict[str, Any]:
        """Poll async ingestion status until completion or timeout."""
        terminal_states = {"completed", "finished", "failed"}
        started = time.monotonic()

        while time.monotonic() - started < timeout_seconds:
            result = self._get_json(f"/jobs/{job_id}", timeout=30)
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
    def _format_request_exception(exc: requests.RequestException) -> Dict[str, Any]:
        """Normalize request errors while preserving JSON error payloads."""
        response = exc.response
        if response is not None:
            parsed = MainWindow._parse_json_response(response)
            if isinstance(parsed, dict):
                parsed.setdefault("error", str(exc))
                return parsed
        return {"error": str(exc)}

    @staticmethod
    def _parse_json_response(response: Response) -> Dict[str, Any] | None:
        """Parse JSON response safely and return a dictionary when possible."""
        try:
            payload = response.json()
        except ValueError:
            return None
        if isinstance(payload, dict):
            return payload
        return None


def launch_ui(api_base_url: str = "http://127.0.0.1:8000") -> None:
    """Start Qt application."""
    app = QApplication(sys.argv)
    app.setApplicationName("RAG Hybrid Response Validator")
    window = MainWindow(api_base_url=api_base_url)
    window.show()
    app.exec()
