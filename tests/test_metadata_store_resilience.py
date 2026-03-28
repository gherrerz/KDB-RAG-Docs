"""Resilience tests for SQLite metadata store lifecycle events."""

from __future__ import annotations

import shutil

from coderag.storage.metadata_store import MetadataStore


def test_touch_job_recovers_after_storage_dir_removed(tmp_path) -> None:
    """Ensure DB reconnect works after storage directory is deleted."""
    db_path = tmp_path / "storage" / "metadata.db"
    store = MetadataStore(db_path)

    first = store.touch_job("job-1", "queued", "first")
    assert first.job_id == "job-1"

    shutil.rmtree(db_path.parent)

    second = store.touch_job("job-2", "queued", "second")
    assert second.job_id == "job-2"
    assert db_path.exists()
    assert store.get_job("job-2") is not None
