"""Tests for configurable RQ ingest timeout behavior."""

from __future__ import annotations

from typing import Any, Dict

import pytest

from coderag.core.settings import Settings
from coderag.jobs import queue


def test_rq_ingest_timeout_default() -> None:
    """Use 900 seconds as default RQ ingest timeout."""
    settings = Settings()
    assert settings.rq_ingest_job_timeout_sec == 900


def test_rq_ingest_timeout_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Read RQ timeout from environment variable when provided."""
    monkeypatch.setenv("RQ_INGEST_JOB_TIMEOUT_SEC", "1800")
    settings = Settings()
    assert settings.rq_ingest_job_timeout_sec == 1800


def test_rq_ingest_timeout_rejects_non_positive() -> None:
    """Reject invalid non-positive timeout values."""
    with pytest.raises(ValueError):
        Settings(rq_ingest_job_timeout_sec=0)


class _DummyRedis:
    @classmethod
    def from_url(cls, _: str) -> object:
        return object()


class _DummyJob:
    def __init__(self, job_id: str) -> None:
        self.id = job_id


class _DummyQueue:
    last_enqueue: Dict[str, Any] = {}

    def __init__(self, name: str, connection: object) -> None:
        self.name = name
        self.connection = connection

    def enqueue(self, func: object, *args: object, **kwargs: object) -> _DummyJob:
        _DummyQueue.last_enqueue = {
            "func": func,
            "args": args,
            "kwargs": kwargs,
            "queue": self.name,
        }
        return _DummyJob(str(kwargs.get("job_id", "job")))


def test_enqueue_ingest_job_passes_configured_timeout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Propagate configured timeout to queue.enqueue job_timeout."""
    monkeypatch.setattr(
        queue,
        "_load_rq_modules",
        lambda: (_DummyRedis, _DummyQueue, object),
    )
    monkeypatch.setattr(
        queue.RUNTIME.store,
        "touch_job",
        lambda *args, **kwargs: None,
    )

    original_timeout = queue.SETTINGS.rq_ingest_job_timeout_sec
    queue.SETTINGS.rq_ingest_job_timeout_sec = 1234
    try:
        job_id = queue.enqueue_ingest_job(
            {
                "source": {
                    "source_type": "folder",
                    "local_path": "sample_data",
                }
            }
        )
        assert isinstance(job_id, str)
        assert _DummyQueue.last_enqueue["kwargs"]["job_timeout"] == 1234
    finally:
        queue.SETTINGS.rq_ingest_job_timeout_sec = original_timeout
