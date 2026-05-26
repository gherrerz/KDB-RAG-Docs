"""Pytest bootstrap for src layout imports."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest


TEST_REMOTE_CHROMA_HOST = "127.0.0.1"
TEST_REMOTE_CHROMA_PORT = "8001"
TEST_REMOTE_CHROMA_COLLECTION = "coderag_chunks_pytest"
TEST_POSTGRES_HOST = "127.0.0.1"
TEST_POSTGRES_PORT = "5432"
TEST_POSTGRES_DB = "coderag_docs"
TEST_POSTGRES_USER = "coderag"
TEST_POSTGRES_PASSWORD = "coderag"


def _ensure_src_on_path() -> None:
    """Prepend src path so tests can import coderag package."""
    repo_root = Path(__file__).resolve().parents[1]
    src_dir = repo_root / "src"
    if not src_dir.exists():
        return
    src_path = str(src_dir)
    if src_path not in sys.path:
        sys.path.insert(0, src_path)


def _set_remote_test_env_defaults() -> None:
    """Default test runtime to the local remote Chroma service."""
    defaults = {
        "USE_CHROMA": "true",
        "CHROMA_MODE": "remote",
        "CHROMA_HOST": TEST_REMOTE_CHROMA_HOST,
        "CHROMA_PORT": TEST_REMOTE_CHROMA_PORT,
        "CHROMA_COLLECTION": TEST_REMOTE_CHROMA_COLLECTION,
        "POSTGRES_HOST": TEST_POSTGRES_HOST,
        "POSTGRES_PORT": TEST_POSTGRES_PORT,
        "POSTGRES_DB": TEST_POSTGRES_DB,
        "POSTGRES_USER": TEST_POSTGRES_USER,
        "POSTGRES_PASSWORD": TEST_POSTGRES_PASSWORD,
        "LEXICAL_FTS_LANGUAGE": "english",
        "NEO4J_URI": "bolt://127.0.0.1:17687",
        "NEO4J_USER": "neo4j",
        "NEO4J_PASSWORD": "password",
        "RUNTIME_ENVIRONMENT": "test",
    }
    for key, value in defaults.items():
        os.environ.setdefault(key, value)


def _clear_remote_test_collection() -> None:
    """Drop the shared pytest Chroma collection when the service is up."""
    try:
        import chromadb

        client = chromadb.HttpClient(
            host=os.environ.get("CHROMA_HOST", TEST_REMOTE_CHROMA_HOST),
            port=int(
                os.environ.get("CHROMA_PORT", TEST_REMOTE_CHROMA_PORT)
            ),
        )
    except Exception:
        return

    try:
        client.delete_collection(
            name=os.environ.get(
                "CHROMA_COLLECTION",
                TEST_REMOTE_CHROMA_COLLECTION,
            )
        )
    except Exception:
        pass
    finally:
        close = getattr(client, "close", None)
        if callable(close):
            close()


_ensure_src_on_path()
_set_remote_test_env_defaults()


@pytest.fixture(autouse=True)
def _remote_chroma_collection_isolation() -> None:
    """Keep the shared remote pytest collection clean between tests."""
    _clear_remote_test_collection()
    try:
        yield
    finally:
        _clear_remote_test_collection()
