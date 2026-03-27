"""Main desktop window combining ingestion and query views."""

from __future__ import annotations

import sys
import time
from typing import Any, Dict

import requests
from requests import Response
from PySide6.QtWidgets import QApplication, QMainWindow, QTabWidget

from coderag.ui.ingestion_view import IngestionView
from coderag.ui.query_view import QueryView


class MainWindow(QMainWindow):
    """Main UI shell for the RAG Hybrid Response Validator."""

    def __init__(self, api_base_url: str = "http://127.0.0.1:8000") -> None:
        super().__init__()
        self.api_base_url = api_base_url.rstrip("/")
        self.setWindowTitle("RAG Hybrid Response Validator")
        self.resize(1100, 760)

        tabs = QTabWidget()
        tabs.addTab(IngestionView(self.ingest, self.reset_all), "Ingestion")
        tabs.addTab(QueryView(self.query), "Query")
        self.setCentralWidget(tabs)

    def ingest(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Run ingestion using async job polling when available."""
        async_response = self._post_json(
            "/sources/ingest/async", payload, timeout=15
        )

        if self._is_async_disabled(async_response):
            # Fallback keeps compatibility when USE_RQ is disabled.
            return self._post_json("/sources/ingest", payload, timeout=3600)

        job_id = async_response.get("job_id")
        if not isinstance(job_id, str) or not job_id:
            return async_response

        poll_result = self._poll_job(job_id, timeout_seconds=3600)
        if isinstance(poll_result, dict):
            poll_result.setdefault("job_id", job_id)
        return poll_result

    def query(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Call backend query endpoint."""
        return self._post_json("/query", payload, timeout=60)

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

    def _poll_job(self, job_id: str, timeout_seconds: int) -> Dict[str, Any]:
        """Poll async ingestion status until completion or timeout."""
        terminal_states = {"completed", "finished", "failed"}
        started = time.monotonic()

        while time.monotonic() - started < timeout_seconds:
            result = self._get_json(f"/jobs/{job_id}", timeout=30)
            status = str(result.get("status", "")).strip().lower()

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
    def _is_async_disabled(response: Dict[str, Any]) -> bool:
        """Detect whether backend rejected async ingestion by configuration."""
        detail = response.get("detail")
        if isinstance(detail, str) and (
            "async ingestion disabled" in detail.strip().lower()
        ):
            return True

        error = response.get("error")
        if not isinstance(error, str):
            return False
        return "async ingestion disabled" in error.strip().lower()

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
    window = MainWindow(api_base_url=api_base_url)
    window.show()
    app.exec()
