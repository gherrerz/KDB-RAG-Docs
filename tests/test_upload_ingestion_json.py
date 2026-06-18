"""Pruebas del colector byte-oriented usado por la ingesta JSON (base64)."""

import io
from pathlib import Path

import pytest
from fastapi import UploadFile

from coderag.api.upload_ingestion import (
    UploadIngestionAdapter,
    UploadIngestionError,
)


def _adapter(tmp_path: Path, max_bytes: int = 1024) -> UploadIngestionAdapter:
    return UploadIngestionAdapter(base_dir=tmp_path, max_upload_bytes=max_bytes)


def test_collect_payloads_round_trip(tmp_path: Path) -> None:
    """El contenido en memoria se captura intacto en el StagedUploadFile."""
    adapter = _adapter(tmp_path)
    content = "hola mundo".encode("utf-8")

    captured = adapter.collect_payloads([("a.txt", content, "text/plain")])

    assert len(captured) == 1
    item = captured[0]
    assert item.staged_filename == "a.txt"
    assert item.payload == content
    assert item.size_bytes == len(content)
    assert item.media_type == "text/plain"


def test_collect_payloads_dedupes_filenames(tmp_path: Path) -> None:
    """Nombres repetidos dentro del batch se desambiguan igual que multipart."""
    adapter = _adapter(tmp_path)

    captured = adapter.collect_payloads(
        [("a.txt", b"x", None), ("a.txt", b"y", None)]
    )

    names = {item.staged_filename for item in captured}
    assert names == {"a.txt", "a_2.txt"}


def test_collect_payloads_rejects_unsupported_extension(tmp_path: Path) -> None:
    adapter = _adapter(tmp_path)
    with pytest.raises(UploadIngestionError):
        adapter.collect_payloads([("malware.exe", b"x", None)])


def test_collect_payloads_rejects_oversize(tmp_path: Path) -> None:
    adapter = _adapter(tmp_path, max_bytes=4)
    with pytest.raises(UploadIngestionError):
        adapter.collect_payloads([("a.txt", b"too-big-payload", None)])


def test_collect_payloads_rejects_empty_batch(tmp_path: Path) -> None:
    adapter = _adapter(tmp_path)
    with pytest.raises(UploadIngestionError):
        adapter.collect_payloads([])


def test_collect_uploads_matches_collect_payloads(tmp_path: Path) -> None:
    """Tras el refactor, la vía multipart y la byte-oriented coinciden."""
    adapter = _adapter(tmp_path)
    content = b"contenido de prueba"

    upload = UploadFile(filename="doc.md", file=io.BytesIO(content))
    from_multipart = adapter.collect_uploads([upload])
    from_payloads = adapter.collect_payloads([("doc.md", content, None)])

    assert from_multipart[0].staged_filename == from_payloads[0].staged_filename
    assert from_multipart[0].payload == from_payloads[0].payload
    assert from_multipart[0].content_hash == from_payloads[0].content_hash


def test_json_endpoint_rejects_invalid_base64() -> None:
    """content_base64 corrupto se rechaza con 422 antes de tocar la ingesta."""
    from fastapi.testclient import TestClient

    from coderag.api.server import app

    client = TestClient(app)
    resp = client.post(
        "/sources/ingest/files/json",
        json={"files": [{"filename": "a.txt", "content_base64": "!!!notb64!!!"}]},
    )
    assert resp.status_code == 422
    assert "content_base64" in resp.text


def test_materialize_batch_writes_files(tmp_path: Path) -> None:
    """materialize_batch escribe los payloads capturados a un dir aislado."""
    adapter = _adapter(tmp_path)
    captured = adapter.collect_payloads([("a.txt", b"data", None)])

    batch = adapter.materialize_batch(captured)

    written = batch.staged_dir / "a.txt"
    assert written.read_bytes() == b"data"
    adapter.cleanup(batch.staged_dir)
    assert not batch.staged_dir.exists()
