"""Job-status service extracted from the application facade."""

from __future__ import annotations

from collections.abc import Callable

from coderag.core.protocols import RuntimeStoreProtocol


class JobApplicationService:
    """Read and normalize persisted async job state for API/UI callers."""

    def __init__(
        self,
        *,
        store: RuntimeStoreProtocol,
        as_public_timed_payload: Callable[[dict[str, object]], dict[str, object]],
    ) -> None:
        """Build job service from shared store and payload normalizer."""
        self._store = store
        self._as_public_timed_payload = as_public_timed_payload

    def get_job(self, job_id: str) -> dict[str, object] | None:
        """Retrieve one job status payload by id."""
        job = self._store.get_job(job_id)
        if job is None:
            return None
        events = self._store.list_job_events(job_id)
        progress_pct = 0.0
        if events:
            last_details = events[-1].get("details", {})
            if isinstance(last_details, dict):
                pct = last_details.get("progress_pct")
                if isinstance(pct, (int, float)):
                    progress_pct = float(pct)
        if job.status == "completed":
            progress_pct = 100.0

        public_events = [
            self._as_public_timed_payload(event)
            for event in events
        ]

        return {
            "job_id": job.job_id,
            "status": job.status,
            "message": job.message,
            "created_at": job.created_at.isoformat(),
            "updated_at": job.updated_at.isoformat(),
            "progress_pct": round(progress_pct, 2),
            "steps": public_events,
        }